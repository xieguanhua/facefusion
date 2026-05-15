import os
import subprocess
import json
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Deque, Dict, Iterator, Optional

import cv2
import numpy
from tqdm import tqdm

from facefusion import ffmpeg_builder, logger, state_manager, translator
from facefusion.audio import create_empty_audio_frame
from facefusion.content_analyser import analyse_stream
from facefusion.ffmpeg import open_ffmpeg
from facefusion.filesystem import is_directory
from facefusion.processors.core import get_processors_modules
from facefusion.types import Fps, StreamMode, VisionFrame
from facefusion.vision import extract_vision_mask, read_static_images

WINDOWS_AUDIO_DEVICE_NAME : Optional[str] = None


def debug_log(hypothesis_id : str, location : str, message : str, data : Dict[str, Any]) -> None:
	try:
		with open('F:/facefusion/debug-b5f084.log', 'a', encoding = 'utf-8') as debug_file:
			# region agent log
			debug_file.write(json.dumps(
			{
				'sessionId': 'b5f084',
				'runId': 'pre-fix',
				'hypothesisId': hypothesis_id,
				'location': location,
				'message': message,
				'data': data,
				'timestamp': int(time.time() * 1000)
			}, ensure_ascii = True) + '\n')
			# endregion
	except Exception:
		pass


def multi_process_capture(camera_capture : cv2.VideoCapture, camera_fps : Fps) -> Iterator[VisionFrame]:
	capture_deque : Deque[VisionFrame] = deque(maxlen = 1)

	with tqdm(desc = translator.get('streaming'), unit = 'frame', disable = state_manager.get_item('log_level') in [ 'warn', 'error' ]) as progress:
		# Realtime mode: keep only one in-flight frame to prevent delay accumulation.
		max_pending_futures = 1
		with ThreadPoolExecutor(max_workers = 1) as executor:
			futures = []

			while camera_capture and camera_capture.isOpened():
				_, capture_vision_frame = camera_capture.read()
				if analyse_stream(capture_vision_frame, camera_fps):
					continue

				if numpy.any(capture_vision_frame) and len(futures) < max_pending_futures:
					future = executor.submit(process_stream_frame, capture_vision_frame)
					futures.append(future)

				for future_done in [ future for future in futures if future.done() ]:
					capture_vision_frame = future_done.result()
					capture_deque.append(capture_vision_frame)
					futures.remove(future_done)

				if capture_deque:
					progress.update()
					yield capture_deque.popleft()


def resolve_windows_audio_device_name() -> Optional[str]:
	global WINDOWS_AUDIO_DEVICE_NAME

	if WINDOWS_AUDIO_DEVICE_NAME:
		return WINDOWS_AUDIO_DEVICE_NAME
	try:
		process = subprocess.run(
			[ 'ffmpeg', '-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy' ],
			capture_output = True,
			text = True,
			encoding = 'utf-8',
			errors = 'ignore'
		)
		output = (process.stdout or '') + '\n' + (process.stderr or '')
		for line in output.splitlines():
			if '(audio)' in line and '"' in line:
				parts = line.split('"')
				if len(parts) >= 2 and parts[1].strip():
					WINDOWS_AUDIO_DEVICE_NAME = parts[1].strip()
					return WINDOWS_AUDIO_DEVICE_NAME
	except Exception:
		return None
	return None


def process_stream_frame(target_vision_frame : VisionFrame) -> VisionFrame:
	source_vision_frames = read_static_images(state_manager.get_item('source_paths'))
	source_audio_frame = create_empty_audio_frame()
	source_voice_frame = create_empty_audio_frame()
	temp_vision_frame = target_vision_frame.copy()
	temp_vision_mask = extract_vision_mask(temp_vision_frame)

	for processor_module in get_processors_modules(state_manager.get_item('processors')):
		logger.disable()
		if processor_module.pre_process('stream'):
			logger.enable()
			temp_vision_frame, temp_vision_mask = processor_module.process_frame(
			{
				'source_vision_frames': source_vision_frames,
				'source_audio_frame': source_audio_frame,
				'source_voice_frame': source_voice_frame,
				'target_vision_frame': target_vision_frame,
				'temp_vision_frame': temp_vision_frame,
				'temp_vision_mask': temp_vision_mask
			})
		logger.enable()

	return temp_vision_frame


def open_stream(stream_mode : StreamMode, stream_resolution : str, stream_fps : Fps, stream_audio : bool = False, audio_filter : Optional[str] = None) -> subprocess.Popen[bytes]:
	commands = ffmpeg_builder.chain(
		ffmpeg_builder.capture_video(),
		ffmpeg_builder.set_media_resolution(stream_resolution),
		ffmpeg_builder.set_input_fps(stream_fps),
		ffmpeg_builder.set_input('-')
	)

	if stream_mode == 'udp':
		if stream_audio and os.name == 'nt':
			audio_device_name = resolve_windows_audio_device_name()
			if audio_device_name:
				commands.extend([ '-f', 'dshow', '-i', 'audio=' + audio_device_name, '-map', '0:v:0', '-map', '1:a:0' ])
			if audio_filter:
				commands.extend([ '-af', audio_filter ])
			if audio_device_name:
				commands.extend([ '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000' ])

		commands.extend(
		[
			'-fflags', 'nobuffer',
			'-flags', 'low_delay',
			'-c:v', 'libx264',
			'-preset', 'ultrafast',
			'-tune', 'zerolatency',
			'-pix_fmt', 'yuv420p',
			'-g', str(stream_fps),
			'-keyint_min', str(stream_fps),
			'-sc_threshold', '0',
			'-x264-params', 'repeat-headers=1:aud=1',
			'-bf', '0',
			'-flush_packets', '1',
			'-muxdelay', '0',
			'-muxpreload', '0',
			'-max_delay', '0'
		])

		commands.extend(ffmpeg_builder.set_stream_mode('udp'))
		commands.extend(ffmpeg_builder.set_stream_quality(2000))
		commands.extend(ffmpeg_builder.set_output('udp://127.0.0.1:27000?pkt_size=1316'))
		# region agent log
		debug_log('H3', 'streamer.py:open_stream', 'udp stream command prepared',
		{
			'streamMode': stream_mode,
			'streamAudio': stream_audio,
			'osName': os.name,
			'windowsAudioDeviceName': resolve_windows_audio_device_name() if stream_audio and os.name == 'nt' else None,
			'audioFilterProvided': bool(audio_filter),
			'afFlagPresent': '-af' in commands,
			'outputTarget': 'udp://127.0.0.1:27000?pkt_size=1316'
		})
		# endregion

	if stream_mode == 'v4l2':
		device_directory_path = '/sys/devices/virtual/video4linux'
		commands.extend(ffmpeg_builder.set_input('-'))
		commands.extend(ffmpeg_builder.set_stream_mode('v4l2'))

		if is_directory(device_directory_path):
			device_names = os.listdir(device_directory_path)

			for device_name in device_names:
				device_path = '/dev/' + device_name
				commands.extend(ffmpeg_builder.set_output(device_path))

		else:
			logger.error(translator.get('stream_not_loaded').format(stream_mode = stream_mode), __name__)

	process = open_ffmpeg(commands)
	# region agent log
	debug_log('H4', 'streamer.py:open_stream', 'ffmpeg process opened',
	{
		'streamMode': stream_mode,
		'pid': process.pid if process else None
	})
	# endregion
	return process
