import json
import time
from typing import Any, Dict, Optional

from facefusion import logger, state_manager, translator
from facefusion.filesystem import is_file

VOICE_CHANGER_READY = False


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


def prepare_webcam_voice_changer() -> bool:
	global VOICE_CHANGER_READY

	model_path = state_manager.get_item('webcam_voice_model_path')
	model_index_path = state_manager.get_item('webcam_voice_model_index_path')

	VOICE_CHANGER_READY = is_file(model_path)
	if model_index_path:
		VOICE_CHANGER_READY = VOICE_CHANGER_READY and is_file(model_index_path)
	# region agent log
	debug_log('H1', 'voice_changer.py:prepare_webcam_voice_changer', 'voice changer readiness evaluated',
	{
		'modelPath': model_path,
		'modelPathExists': is_file(model_path),
		'modelIndexPath': model_index_path,
		'modelIndexPathExists': is_file(model_index_path) if model_index_path else None,
		'voiceChangerReady': VOICE_CHANGER_READY
	})
	# endregion
	if not VOICE_CHANGER_READY:
		logger.warn(translator.get('webcam_voice_model_unavailable'), __name__)
	return VOICE_CHANGER_READY


def create_audio_filter() -> Optional[str]:
	if not VOICE_CHANGER_READY:
		# region agent log
		debug_log('H2', 'voice_changer.py:create_audio_filter', 'audio filter skipped because voice changer is not ready',
		{
			'voiceChangerReady': VOICE_CHANGER_READY
		})
		# endregion
		return None

	webcam_voice_pitch = state_manager.get_item('webcam_voice_pitch') or 0

	if not isinstance(webcam_voice_pitch, int):
		webcam_voice_pitch = int(webcam_voice_pitch)
	if webcam_voice_pitch == 0:
		# region agent log
		debug_log('H2', 'voice_changer.py:create_audio_filter', 'audio filter skipped because pitch is zero',
		{
			'webcamVoicePitch': webcam_voice_pitch
		})
		# endregion
		return None

	pitch_factor = 2 ** (webcam_voice_pitch / 12)
	if pitch_factor <= 0:
		# region agent log
		debug_log('H2', 'voice_changer.py:create_audio_filter', 'audio filter skipped because pitch factor is invalid',
		{
			'webcamVoicePitch': webcam_voice_pitch,
			'pitchFactor': pitch_factor
		})
		# endregion
		return None
	audio_filter = 'asetrate=48000*' + str(pitch_factor) + ',aresample=48000,atempo=' + str(1 / pitch_factor)
	# region agent log
	debug_log('H2', 'voice_changer.py:create_audio_filter', 'audio filter created',
	{
		'webcamVoicePitch': webcam_voice_pitch,
		'pitchFactor': pitch_factor,
		'audioFilter': audio_filter
	})
	# endregion
	return audio_filter
