import os
from typing import Optional

import gradio

from facefusion import translator
from facefusion.camera_manager import detect_local_camera_ids
from facefusion.common_helper import get_first
from facefusion.types import WebcamMode
from facefusion.uis import choices as uis_choices
from facefusion.uis.core import register_ui_component

WEBCAM_DEVICE_ID_DROPDOWN : Optional[gradio.Dropdown] = None
WEBCAM_MODE_RADIO : Optional[gradio.Radio] = None
WEBCAM_RESOLUTION_DROPDOWN : Optional[gradio.Dropdown] = None
WEBCAM_FPS_SLIDER : Optional[gradio.Slider] = None
WEBCAM_STREAM_TARGET_TEXTBOX : Optional[gradio.Textbox] = None


def render() -> None:
	global WEBCAM_DEVICE_ID_DROPDOWN
	global WEBCAM_MODE_RADIO
	global WEBCAM_RESOLUTION_DROPDOWN
	global WEBCAM_FPS_SLIDER
	global WEBCAM_STREAM_TARGET_TEXTBOX

	local_camera_ids = detect_local_camera_ids(0, 10) or [ 'none' ] #type:ignore[list-item]
	WEBCAM_DEVICE_ID_DROPDOWN = gradio.Dropdown(
		value = get_first(local_camera_ids),
		label = translator.get('uis.webcam_device_id_dropdown'),
		choices = local_camera_ids
	)
	WEBCAM_MODE_RADIO = gradio.Radio(
		label = translator.get('uis.webcam_mode_radio'),
		choices = uis_choices.webcam_modes,
		value = uis_choices.webcam_modes[0]
	)
	WEBCAM_RESOLUTION_DROPDOWN = gradio.Dropdown(
		label = translator.get('uis.webcam_resolution_dropdown'),
		choices = uis_choices.webcam_resolutions,
		value = uis_choices.webcam_resolutions[0]
	)
	WEBCAM_FPS_SLIDER = gradio.Slider(
		label = translator.get('uis.webcam_fps_slider'),
		value = 30,
		step = 1,
		minimum = 1,
		maximum = 30
	)
	WEBCAM_STREAM_TARGET_TEXTBOX = gradio.Textbox(
		label = translator.get('uis.webcam_stream_target_textbox'),
		value = resolve_stream_target(uis_choices.webcam_modes[0]),
		interactive = False
	)
	register_ui_component('webcam_device_id_dropdown', WEBCAM_DEVICE_ID_DROPDOWN)
	register_ui_component('webcam_mode_radio', WEBCAM_MODE_RADIO)
	register_ui_component('webcam_resolution_dropdown', WEBCAM_RESOLUTION_DROPDOWN)
	register_ui_component('webcam_fps_slider', WEBCAM_FPS_SLIDER)
	register_ui_component('webcam_stream_target_textbox', WEBCAM_STREAM_TARGET_TEXTBOX)


def listen() -> None:
	WEBCAM_MODE_RADIO.change(update_webcam_stream_target, inputs = WEBCAM_MODE_RADIO, outputs = WEBCAM_STREAM_TARGET_TEXTBOX)


def update_webcam_stream_target(webcam_mode : WebcamMode) -> gradio.Textbox:
	return gradio.Textbox(value = resolve_stream_target(webcam_mode))


def resolve_stream_target(webcam_mode : WebcamMode) -> str:
	if webcam_mode == 'inline':
		return 'inline preview only'
	if webcam_mode == 'udp':
		return 'udp://localhost:27000?pkt_size=1316'
	if webcam_mode == 'v4l2':
		if os.name == 'posix':
			return '/dev/video*'
		return 'v4l2 device path is available on Linux only'
	return ''
