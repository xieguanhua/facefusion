import subprocess
from typing import Iterator, List, Optional, Tuple

import cv2
import gradio
import json
import numpy
import time

from facefusion import state_manager, translator, voice_changer
from facefusion.camera_manager import clear_camera_pool, get_local_camera_capture
from facefusion.filesystem import has_image
from facefusion.streamer import multi_process_capture, open_stream
from facefusion.types import Fps, VisionFrame, WebcamMode
from facefusion.uis.core import get_ui_component
from facefusion.uis.types import File
from facefusion.vision import fit_cover_frame, unpack_resolution

SOURCE_FILE : Optional[gradio.File] = None
WEBCAM_IMAGE : Optional[gradio.Image] = None
WEBCAM_START_BUTTON : Optional[gradio.Button] = None
WEBCAM_STOP_BUTTON : Optional[gradio.Button] = None
WEBCAM_STREAM : Optional[subprocess.Popen[bytes]] = None


def debug_log(hypothesis_id : str, location : str, message : str, data : dict) -> None:
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


def render() -> None:
	global SOURCE_FILE
	global WEBCAM_IMAGE
	global WEBCAM_START_BUTTON
	global WEBCAM_STOP_BUTTON

	has_source_image = has_image(state_manager.get_item('source_paths'))
	SOURCE_FILE = gradio.File(
		label = translator.get('uis.source_file'),
		file_count = 'multiple',
		value = state_manager.get_item('source_paths') if has_source_image else None
	)
	WEBCAM_IMAGE = gradio.Image(
		label = translator.get('uis.webcam_image'),
		format = 'jpeg',
		visible = False
	)
	WEBCAM_START_BUTTON = gradio.Button(
		value = translator.get('uis.start_button'),
		variant = 'primary',
		size = 'sm'
	)
	WEBCAM_STOP_BUTTON = gradio.Button(
		value = translator.get('uis.stop_button'),
		size = 'sm',
		visible = False
	)


def listen() -> None:
	SOURCE_FILE.change(update_source, inputs = SOURCE_FILE, outputs = SOURCE_FILE)
	webcam_device_id_dropdown = get_ui_component('webcam_device_id_dropdown')
	webcam_mode_radio = get_ui_component('webcam_mode_radio')
	webcam_resolution_dropdown = get_ui_component('webcam_resolution_dropdown')
	webcam_fps_slider = get_ui_component('webcam_fps_slider')

	if webcam_device_id_dropdown and webcam_mode_radio and webcam_resolution_dropdown and webcam_fps_slider:
		WEBCAM_START_BUTTON.click(pre_start, outputs = [ SOURCE_FILE, WEBCAM_IMAGE, WEBCAM_START_BUTTON, WEBCAM_STOP_BUTTON ])
		start_event = WEBCAM_START_BUTTON.click(start, inputs = [ webcam_device_id_dropdown, webcam_mode_radio, webcam_resolution_dropdown, webcam_fps_slider ], outputs = WEBCAM_IMAGE)
		start_event.then(pre_stop)
		WEBCAM_STOP_BUTTON.click(stop, cancels = start_event, outputs = WEBCAM_IMAGE)
		WEBCAM_STOP_BUTTON.click(pre_stop, outputs = [ SOURCE_FILE, WEBCAM_IMAGE, WEBCAM_START_BUTTON, WEBCAM_STOP_BUTTON ])


def update_source(files : List[File]) -> gradio.File:
	file_names = [ file.name for file in files ] if files else None
	has_source_image = has_image(file_names)

	if has_source_image:
		state_manager.set_item('source_paths', file_names)
		return gradio.File(value = file_names)

	state_manager.clear_item('source_paths')
	return gradio.File(value = None)


def pre_start() -> Tuple[gradio.File, gradio.Image, gradio.Button, gradio.Button]:
	return gradio.File(visible = False), gradio.Image(visible = True), gradio.Button(visible = False), gradio.Button(visible = True)


def pre_stop() -> Tuple[gradio.File, gradio.Image, gradio.Button, gradio.Button]:
	# region agent log
	debug_log('H1', 'webcam.py:pre_stop', 'pre_stop called', {})
	# endregion
	return gradio.File(visible = True), gradio.Image(visible = False), gradio.Button(visible = True), gradio.Button(visible = False)


def close_webcam_stream() -> None:
	global WEBCAM_STREAM

	if not WEBCAM_STREAM:
		return None
	try:
		if WEBCAM_STREAM.stdin:
			WEBCAM_STREAM.stdin.close()
	except Exception:
		pass
	try:
		if WEBCAM_STREAM.poll() is None:
			WEBCAM_STREAM.terminate()
			WEBCAM_STREAM.wait(timeout = 1)
	except Exception:
		try:
			if WEBCAM_STREAM.poll() is None:
				WEBCAM_STREAM.kill()
		except Exception:
			pass
	WEBCAM_STREAM = None


def start(webcam_device_id : int, webcam_mode : WebcamMode, webcam_resolution : str, webcam_fps : Fps) -> Iterator[VisionFrame]:
	state_manager.init_item('face_selector_mode', 'one')
	state_manager.sync_state()
	# region agent log
	debug_log('H5', 'webcam.py:start', 'webcam start called',
	{
		'webcamDeviceId': webcam_device_id,
		'webcamMode': webcam_mode,
		'webcamResolution': webcam_resolution,
		'webcamFps': webcam_fps,
		'webcamVoicePitch': state_manager.get_item('webcam_voice_pitch')
	})
	# endregion

	camera_capture = get_local_camera_capture(webcam_device_id)
	if not camera_capture or not camera_capture.isOpened():
		clear_camera_pool()
		camera_capture = get_local_camera_capture(webcam_device_id)
	stream = None
	close_webcam_stream()
	# region agent log
	debug_log('H2', 'webcam.py:start', 'camera capture fetched',
	{
		'cameraCaptureExists': camera_capture is not None,
		'cameraCaptureOpened': bool(camera_capture and camera_capture.isOpened()),
		'webcamMode': webcam_mode
	})
	# endregion

	if webcam_mode in [ 'udp', 'v4l2' ]:
		global WEBCAM_STREAM
		voice_changer.prepare_webcam_voice_changer()
		audio_filter = voice_changer.create_audio_filter()
		stream = open_stream(webcam_mode, webcam_resolution, webcam_fps, webcam_mode == 'udp', audio_filter) #type:ignore[arg-type]
		WEBCAM_STREAM = stream
	webcam_width, webcam_height = unpack_resolution(webcam_resolution)

	if camera_capture and camera_capture.isOpened():
		try:
			camera_capture.set(cv2.CAP_PROP_FRAME_WIDTH, webcam_width)
			camera_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, webcam_height)
			camera_capture.set(cv2.CAP_PROP_FPS, webcam_fps)
			stream_error_logged = False

			for capture_vision_frame in multi_process_capture(camera_capture, webcam_fps):
				capture_vision_frame = cv2.cvtColor(capture_vision_frame, cv2.COLOR_BGR2RGB)
				capture_vision_frame = fit_cover_frame(capture_vision_frame, (webcam_width, webcam_height))

				yield capture_vision_frame
				if webcam_mode in [ 'udp', 'v4l2' ]:
					try:
						stream_vision_frame = capture_vision_frame
						if stream_vision_frame.dtype != numpy.uint8:
							stream_vision_frame = numpy.clip(stream_vision_frame, 0, 255).astype(numpy.uint8)
						if stream_vision_frame.shape[0] != webcam_height or stream_vision_frame.shape[1] != webcam_width:
							stream_vision_frame = cv2.resize(stream_vision_frame, (webcam_width, webcam_height))
						stream_vision_frame = numpy.ascontiguousarray(stream_vision_frame)
						stream.stdin.write(stream_vision_frame.tobytes())
					except Exception as exception:
						if not stream_error_logged:
							# region agent log
							debug_log('H4', 'webcam.py:start', 'stream stdin write failed',
							{
								'webcamMode': webcam_mode,
								'exceptionType': type(exception).__name__,
								'exceptionMessage': str(exception)
							})
							# endregion
							# Keep audio stream alive by retrying once without pitch filter.
							if webcam_mode == 'udp' and audio_filter:
								try:
									close_webcam_stream()
									stream = open_stream(webcam_mode, webcam_resolution, webcam_fps, True, None) #type:ignore[arg-type]
									WEBCAM_STREAM = stream
									audio_filter = None
									debug_log('H4', 'webcam.py:start', 'stream reopened without audio filter', {})
								except Exception:
									pass
							stream_error_logged = True
						pass
		finally:
			# region agent log
			debug_log('H3', 'webcam.py:start', 'webcam start generator exiting',
			{
				'cameraCaptureOpenedAtExit': bool(camera_capture and camera_capture.isOpened()),
				'streamExists': stream is not None,
				'streamPid': stream.pid if stream else None
			})
			# endregion
			close_webcam_stream()


def stop() -> gradio.Image:
	# region agent log
	debug_log('H1', 'webcam.py:stop', 'webcam stop called', {})
	# endregion
	close_webcam_stream()
	clear_camera_pool()
	# region agent log
	debug_log('H1', 'webcam.py:stop', 'camera pool clear requested', {})
	# endregion
	return gradio.Image(value = None)
