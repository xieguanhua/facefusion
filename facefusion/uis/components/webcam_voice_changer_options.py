import os
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import gradio

from facefusion import download, rvc_model_registry, state_manager, translator
from facefusion.filesystem import create_directory, is_file, resolve_relative_path
from facefusion.rvc_model_registry import RvcModelEntry
from facefusion.types import RvcModelSource
from facefusion.uis.core import register_ui_component

WEBCAM_VOICE_MODEL_SOURCE_DROPDOWN : Optional[gradio.Dropdown] = None
WEBCAM_VOICE_MODEL_DROPDOWN : Optional[gradio.Dropdown] = None
WEBCAM_VOICE_MODEL_REFRESH_BUTTON : Optional[gradio.Button] = None
WEBCAM_VOICE_PITCH_SLIDER : Optional[gradio.Slider] = None

RVC_MODEL_ENTRIES : List[RvcModelEntry] = []


def render() -> None:
	global WEBCAM_VOICE_MODEL_SOURCE_DROPDOWN
	global WEBCAM_VOICE_MODEL_DROPDOWN
	global WEBCAM_VOICE_MODEL_REFRESH_BUTTON
	global WEBCAM_VOICE_PITCH_SLIDER

	init_state()
	refresh_registry(False)
	filtered_entries = get_filtered_entries(state_manager.get_item('webcam_voice_model_source'))
	model_choices = [ rvc_model_registry.format_entry_choice(entry) for entry in filtered_entries ]
	selected_choice = find_selected_choice(model_choices, state_manager.get_item('webcam_voice_model_id'))

	with gradio.Group():
		WEBCAM_VOICE_MODEL_REFRESH_BUTTON = gradio.Button(
			value = '↺',
			size = 'sm',
			elem_classes = [ 'reset-button' ],
			elem_id = 'webcam-voice-model-refresh-button'
		)

		WEBCAM_VOICE_MODEL_SOURCE_DROPDOWN = gradio.Dropdown(
			label = translator.get('uis.webcam_voice_model_source_dropdown'),
			choices = [ 'all', 'huggingface', 'github' ],
			value = state_manager.get_item('webcam_voice_model_source')
		)
		
		WEBCAM_VOICE_MODEL_DROPDOWN = gradio.Dropdown(
			label = translator.get('uis.webcam_voice_model_dropdown'),
			choices = model_choices,
			value = selected_choice
		)
		WEBCAM_VOICE_PITCH_SLIDER = gradio.Slider(
			label = translator.get('uis.webcam_voice_pitch_slider'),
			value = state_manager.get_item('webcam_voice_pitch'),
			step = 1,
			minimum = -12,
			maximum = 12
		)
	register_ui_component('webcam_voice_model_source_dropdown', WEBCAM_VOICE_MODEL_SOURCE_DROPDOWN)
	register_ui_component('webcam_voice_model_dropdown', WEBCAM_VOICE_MODEL_DROPDOWN)
	register_ui_component('webcam_voice_pitch_slider', WEBCAM_VOICE_PITCH_SLIDER)


def listen() -> None:
	WEBCAM_VOICE_MODEL_SOURCE_DROPDOWN.change(
		update_model_source,
		inputs = WEBCAM_VOICE_MODEL_SOURCE_DROPDOWN,
		outputs = WEBCAM_VOICE_MODEL_DROPDOWN,
		show_progress = 'full'
	)
	WEBCAM_VOICE_MODEL_DROPDOWN.change(
		update_model_choice,
		inputs = WEBCAM_VOICE_MODEL_DROPDOWN,
		outputs = WEBCAM_VOICE_MODEL_DROPDOWN,
		show_progress = 'full'
	)
	WEBCAM_VOICE_MODEL_REFRESH_BUTTON.click(
		refresh_model_choices,
		inputs = WEBCAM_VOICE_MODEL_SOURCE_DROPDOWN,
		outputs = WEBCAM_VOICE_MODEL_DROPDOWN,
		show_progress = 'full'
	)
	WEBCAM_VOICE_PITCH_SLIDER.release(update_voice_pitch, inputs = WEBCAM_VOICE_PITCH_SLIDER)


def init_state() -> None:
	if state_manager.get_item('webcam_voice_model_source') is None:
		state_manager.init_item('webcam_voice_model_source', 'all')
	if state_manager.get_item('webcam_voice_model_id') is None:
		state_manager.init_item('webcam_voice_model_id', '')
	if state_manager.get_item('webcam_voice_model_status') is None:
		state_manager.init_item('webcam_voice_model_status', '')
	if state_manager.get_item('webcam_voice_model_path') is None:
		state_manager.init_item('webcam_voice_model_path', '')
	if state_manager.get_item('webcam_voice_model_index_path') is None:
		state_manager.init_item('webcam_voice_model_index_path', '')
	if state_manager.get_item('webcam_voice_pitch') is None:
		state_manager.init_item('webcam_voice_pitch', 0)


def refresh_registry(refresh_remote : bool, model_source : str = 'all') -> bool:
	global RVC_MODEL_ENTRIES

	if refresh_remote:
		RVC_MODEL_ENTRIES, refresh_succeeded = rvc_model_registry.refresh_entries(model_source)
		return refresh_succeeded
	RVC_MODEL_ENTRIES = rvc_model_registry.load_default_entries()
	return True


def get_filtered_entries(model_source : RvcModelSource) -> List[RvcModelEntry]:
	return rvc_model_registry.filter_entries(RVC_MODEL_ENTRIES, model_source)


def find_selected_choice(model_choices : List[str], selected_entry_id : str) -> Optional[str]:
	for model_choice in model_choices:
		if rvc_model_registry.parse_entry_id(model_choice) == selected_entry_id:
			return model_choice
	if model_choices:
		first_choice = model_choices[0]
		state_manager.set_item('webcam_voice_model_id', rvc_model_registry.parse_entry_id(first_choice))
		return first_choice
	state_manager.set_item('webcam_voice_model_id', '')
	return None


def update_model_source(model_source : RvcModelSource) -> gradio.Dropdown:
	state_manager.set_item('webcam_voice_model_source', model_source)
	filtered_entries = get_filtered_entries(model_source)
	model_choices = [ rvc_model_registry.format_entry_choice(entry) for entry in filtered_entries ]
	selected_choice = find_selected_choice(model_choices, state_manager.get_item('webcam_voice_model_id'))
	status_message = translator.get('webcam_voice_model_list_loaded').format(count = len(model_choices))
	state_manager.set_item('webcam_voice_model_status', status_message)
	return gradio.Dropdown(choices = model_choices, value = selected_choice)


def update_model_choice(model_choice : str) -> gradio.Dropdown:
	selected_entry_id = rvc_model_registry.parse_entry_id(model_choice)
	state_manager.set_item('webcam_voice_model_id', selected_entry_id)
	download_model_choice(model_choice)
	filtered_entries = get_filtered_entries(state_manager.get_item('webcam_voice_model_source'))
	model_choices = [ rvc_model_registry.format_entry_choice(entry) for entry in filtered_entries ]
	return gradio.Dropdown(choices = model_choices, value = model_choice)


def refresh_model_choices(model_source : RvcModelSource) -> gradio.Dropdown:
	state_manager.set_item('webcam_voice_model_source', model_source)
	refresh_succeeded = refresh_registry(True, model_source)
	filtered_entries = get_filtered_entries(model_source)
	model_choices = [ rvc_model_registry.format_entry_choice(entry) for entry in filtered_entries ]
	selected_choice = find_selected_choice(model_choices, state_manager.get_item('webcam_voice_model_id'))

	if refresh_succeeded:
		status_message = translator.get('webcam_voice_model_refresh_succeeded').format(count = len(model_choices))
	else:
		status_message = translator.get('webcam_voice_model_refresh_failed')

	state_manager.set_item('webcam_voice_model_status', status_message)
	return gradio.Dropdown(choices = model_choices, value = selected_choice)


def download_model_choice(model_choice : str) -> None:
	selected_entry_id = rvc_model_registry.parse_entry_id(model_choice)
	state_manager.set_item('webcam_voice_model_id', selected_entry_id)
	model_entry = rvc_model_registry.get_entry_by_id(RVC_MODEL_ENTRIES, selected_entry_id)

	if not model_entry:
		status_message = translator.get('webcam_voice_model_not_selected')
		state_manager.set_item('webcam_voice_model_status', status_message)
		return None

	model_url = model_entry.get('model_url')

	if not model_url:
		status_message = translator.get('webcam_voice_model_download_missing_url')
		state_manager.set_item('webcam_voice_model_status', status_message)
		return None

	model_file_path, model_index_path = resolve_local_model_paths(model_entry)
	if model_file_path and is_file(model_file_path) and (not model_index_path or is_file(model_index_path)):
		state_manager.set_item('webcam_voice_model_path', model_file_path)
		state_manager.set_item('webcam_voice_model_index_path', model_index_path)
		status_message = translator.get('webcam_voice_model_already_downloaded').format(model_name = model_entry.get('name'))
		state_manager.set_item('webcam_voice_model_status', status_message)
		return None

	model_directory_path = resolve_relative_path('../.assets/models/rvc/' + model_entry.get('id'))
	create_directory(model_directory_path)

	try:
		model_file_path = download.download_url(model_directory_path, model_url)
		model_index_url = model_entry.get('index_url')
		model_index_path = ''

		if model_index_url:
			model_index_path = download.download_url(model_directory_path, model_index_url)
		if not model_file_path or not is_file(model_file_path):
			raise ValueError('model file is missing')

		state_manager.set_item('webcam_voice_model_path', model_file_path)
		state_manager.set_item('webcam_voice_model_index_path', model_index_path)
		status_message = translator.get('webcam_voice_model_download_succeeded').format(model_name = model_entry.get('name'))
	except Exception as exception:
		status_message = translator.get('webcam_voice_model_download_failed').format(model_name = model_entry.get('name'), reason = str(exception))

	state_manager.set_item('webcam_voice_model_status', status_message)
	return None


def resolve_local_model_paths(model_entry : RvcModelEntry) -> Tuple[str, str]:
	model_directory_path = resolve_relative_path('../.assets/models/rvc/' + model_entry.get('id'))
	model_url = model_entry.get('model_url')
	model_index_url = model_entry.get('index_url')
	model_file_name = os.path.basename(urlparse(model_url).path) if model_url else ''
	model_index_name = os.path.basename(urlparse(model_index_url).path) if model_index_url else ''
	model_file_path = os.path.join(model_directory_path, model_file_name) if model_file_name else ''
	model_index_path = os.path.join(model_directory_path, model_index_name) if model_index_name else ''
	return model_file_path, model_index_path


def update_voice_pitch(webcam_voice_pitch : int) -> None:
	state_manager.set_item('webcam_voice_pitch', webcam_voice_pitch)
