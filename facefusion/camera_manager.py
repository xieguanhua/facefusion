import json
import time
from typing import List

import cv2

from facefusion.types import CameraPoolSet

CAMERA_POOL_SET : CameraPoolSet =\
{
	'capture': {}
}


def debug_log(hypothesis_id : str, location : str, message : str, data : dict) -> None:
	try:
		with open('debug-3d6ddd.log', 'a', encoding = 'utf-8') as debug_file:
			# region agent log
			debug_file.write(json.dumps(
			{
				'sessionId': '3d6ddd',
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


def get_local_camera_capture(camera_id : int) -> cv2.VideoCapture:
	camera_key = str(camera_id)

	if camera_key not in CAMERA_POOL_SET.get('capture'):
		camera_capture = cv2.VideoCapture(camera_id)

		if camera_capture.isOpened():
			CAMERA_POOL_SET['capture'][camera_key] = camera_capture
			# region agent log
			debug_log('H2', 'camera_manager.py:get_local_camera_capture', 'new camera capture opened',
			{
				'cameraId': camera_id,
				'cameraKey': camera_key
			})
			# endregion
		else:
			# region agent log
			debug_log('H2', 'camera_manager.py:get_local_camera_capture', 'new camera capture failed to open',
			{
				'cameraId': camera_id,
				'cameraKey': camera_key
			})
			# endregion
	else:
		# region agent log
		debug_log('H2', 'camera_manager.py:get_local_camera_capture', 'reusing camera capture from pool',
		{
			'cameraId': camera_id,
			'cameraKey': camera_key
		})
		# endregion

	return CAMERA_POOL_SET.get('capture').get(camera_key)


def get_remote_camera_capture(camera_url : str) -> cv2.VideoCapture:
	if camera_url not in CAMERA_POOL_SET.get('capture'):
		camera_capture = cv2.VideoCapture(camera_url)

		if camera_capture.isOpened():
			CAMERA_POOL_SET['capture'][camera_url] = camera_capture

	return CAMERA_POOL_SET.get('capture').get(camera_url)


def clear_camera_pool() -> None:
	# region agent log
	debug_log('H1', 'camera_manager.py:clear_camera_pool', 'clear camera pool begin',
	{
		'captureCountBefore': len(CAMERA_POOL_SET.get('capture'))
	})
	# endregion
	for camera_key, camera_capture in list(CAMERA_POOL_SET.get('capture').items()):
		# region agent log
		debug_log('H1', 'camera_manager.py:clear_camera_pool', 'camera release begin',
		{
			'cameraKey': camera_key,
			'cameraOpenedBeforeRelease': bool(camera_capture and camera_capture.isOpened())
		})
		# endregion
		try:
			camera_capture.release()
			# region agent log
			debug_log('H1', 'camera_manager.py:clear_camera_pool', 'camera release finished',
			{
				'cameraKey': camera_key,
				'cameraOpenedAfterRelease': bool(camera_capture and camera_capture.isOpened())
			})
			# endregion
		except Exception as exception:
			# region agent log
			debug_log('H1', 'camera_manager.py:clear_camera_pool', 'camera release failed',
			{
				'cameraKey': camera_key,
				'exceptionType': type(exception).__name__,
				'exceptionMessage': str(exception)
			})
			# endregion

	CAMERA_POOL_SET['capture'].clear()
	# region agent log
	debug_log('H1', 'camera_manager.py:clear_camera_pool', 'clear camera pool finished',
	{
		'captureCountAfter': len(CAMERA_POOL_SET.get('capture'))
	})
	# endregion


def detect_local_camera_ids(id_start : int, id_end : int) -> List[int]:
	local_camera_ids = []

	for camera_id in range(id_start, id_end):
		cv2.utils.logging.setLogLevel(0)
		camera_capture = get_local_camera_capture(camera_id)
		cv2.utils.logging.setLogLevel(3)

		if camera_capture and camera_capture.isOpened():
			local_camera_ids.append(camera_id)

	return local_camera_ids
