import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from facefusion import json
from facefusion.filesystem import resolve_relative_path


class RvcModelEntry(TypedDict):
	id : str
	name : str
	source : str
	model_url : str
	index_url : str


def get_registry_path() -> str:
	return resolve_relative_path('../.assets/rvc-models.json')


def load_default_entries() -> List[RvcModelEntry]:
	entries = []
	registry_content = json.read_json(get_registry_path())

	if isinstance(registry_content, list):
		for registry_entry in registry_content:
			entry = parse_default_entry(registry_entry)
			if entry:
				entries.append(entry)
	return entries


def parse_default_entry(registry_entry : Any) -> Optional[RvcModelEntry]:
	if not isinstance(registry_entry, dict):
		return None
	model_id = str(registry_entry.get('id') or '').strip()
	model_name = str(registry_entry.get('name') or '').strip()
	model_source = str(registry_entry.get('source') or '').strip().lower()
	model_repo = str(registry_entry.get('repo') or '').strip()
	model_path = str(registry_entry.get('model_path') or '').strip()
	index_path = str(registry_entry.get('index_path') or '').strip()

	if not model_id or not model_name or model_source not in [ 'huggingface', 'github' ] or not model_repo or not model_path:
		return None
	model_url = create_model_url(model_source, model_repo, model_path)
	index_url = create_model_url(model_source, model_repo, index_path) if index_path else ''

	return\
	{
		'id': model_id,
		'name': model_name,
		'source': model_source,
		'model_url': model_url,
		'index_url': index_url
	}


def create_model_url(model_source : str, model_repo : str, file_path : str) -> str:
	if model_source == 'huggingface':
		return 'https://huggingface.co/' + model_repo + '/resolve/main/' + file_path
	if model_source == 'github':
		return 'https://github.com/' + model_repo + '/raw/main/' + file_path
	return ''


def refresh_entries(model_source : str, limit : int = 10) -> Tuple[List[RvcModelEntry], bool]:
	default_entries = load_default_entries()
	remote_entries : List[RvcModelEntry] = []
	refresh_succeeded = False

	try:
		if model_source in [ 'all', 'huggingface' ]:
			remote_entries.extend(fetch_huggingface_entries(limit))
		if model_source in [ 'all', 'github' ]:
			remote_entries.extend(fetch_github_entries(limit))
		refresh_succeeded = True
	except Exception:
		refresh_succeeded = False

	merged_entries = merge_entries(default_entries, remote_entries)
	return merged_entries, refresh_succeeded


def merge_entries(primary_entries : List[RvcModelEntry], secondary_entries : List[RvcModelEntry]) -> List[RvcModelEntry]:
	entries : List[RvcModelEntry] = []
	entry_ids = set()

	for entry in primary_entries + secondary_entries:
		if entry.get('id') not in entry_ids:
			entry_ids.add(entry.get('id'))
			entries.append(entry)
	return entries


def filter_entries(entries : List[RvcModelEntry], model_source : str) -> List[RvcModelEntry]:
	if model_source == 'all':
		return entries
	return [ entry for entry in entries if entry.get('source') == model_source ]


def format_entry_choice(entry : RvcModelEntry) -> str:
	return '[' + entry.get('source').upper() + '] ' + entry.get('name') + ' :: ' + entry.get('id')


def parse_entry_id(entry_choice : str) -> str:
	if entry_choice and '::' in entry_choice:
		return entry_choice.split('::', 1)[1].strip()
	return ''


def get_entry_by_id(entries : List[RvcModelEntry], entry_id : str) -> Optional[RvcModelEntry]:
	for entry in entries:
		if entry.get('id') == entry_id:
			return entry
	return None


def fetch_huggingface_entries(limit : int) -> List[RvcModelEntry]:
	entries : List[RvcModelEntry] = []
	models = request_json_content('https://huggingface.co/api/models?search=RVC&limit=' + str(limit))

	if not isinstance(models, list):
		return entries

	for model in models:
		model_id = str(model.get('id') or '').strip()
		if not model_id:
			continue
		model_content = request_json_content('https://huggingface.co/api/models/' + model_id + '?expand[]=siblings')
		siblings = model_content.get('siblings') if isinstance(model_content, dict) else []

		if not isinstance(siblings, list):
			continue
		for sibling in siblings:
			file_path = str(sibling.get('rfilename') or '').strip()
			if not file_path.lower().endswith('.pth'):
				continue
			file_name = os.path.basename(file_path)
			file_stem, _ = os.path.splitext(file_name)
			index_path = os.path.dirname(file_path) + '/' + file_stem + '.index'
			index_url = ''

			if any(str(candidate.get('rfilename') or '').strip() == index_path for candidate in siblings):
				index_url = 'https://huggingface.co/' + model_id + '/resolve/main/' + index_path

			entries.append(
			{
				'id': 'hf_' + normalize_identifier(model_id + '_' + file_stem),
				'name': model_id + ' / ' + file_name,
				'source': 'huggingface',
				'model_url': 'https://huggingface.co/' + model_id + '/resolve/main/' + file_path,
				'index_url': index_url
			})
	return entries


def fetch_github_entries(limit : int) -> List[RvcModelEntry]:
	entries : List[RvcModelEntry] = []
	# without authentication, GitHub search API can be rate-limited quickly.
	# keep this best-effort and fail-safe.
	search_content = request_json_content('https://api.github.com/search/code?q=RVC+extension:pth&per_page=' + str(limit))
	items = search_content.get('items') if isinstance(search_content, dict) else []

	if not isinstance(items, list):
		return entries
	for item in items:
		repository = item.get('repository') if isinstance(item, dict) else {}
		repository_name = str(repository.get('full_name') or '').strip()
		file_path = str(item.get('path') or '').strip() if isinstance(item, dict) else ''

		if not repository_name or not file_path:
			continue
		file_name = os.path.basename(file_path)
		file_stem, _ = os.path.splitext(file_name)
		contents_url = 'https://api.github.com/repos/' + repository_name + '/contents/' + file_path
		content = request_json_content(contents_url)
		model_url = str(content.get('download_url') or '').strip() if isinstance(content, dict) else ''

		if not model_url:
			continue
		index_url = find_github_index_url(repository_name, file_path, file_stem)
		entries.append(
		{
			'id': 'gh_' + normalize_identifier(repository_name + '_' + file_stem),
			'name': repository_name + ' / ' + file_name,
			'source': 'github',
			'model_url': model_url,
			'index_url': index_url
		})
	return entries


def find_github_index_url(repository_name : str, model_path : str, file_stem : str) -> str:
	directory_path = os.path.dirname(model_path).strip('/')

	if not directory_path:
		return ''
	content = request_json_content('https://api.github.com/repos/' + repository_name + '/contents/' + directory_path)

	if not isinstance(content, list):
		return ''
	for item in content:
		if str(item.get('name') or '').strip() == file_stem + '.index':
			return str(item.get('download_url') or '')
	return ''


def request_json_content(url : str) -> Any:
	request = urllib.request.Request(url, headers = { 'User-Agent': 'facefusion-rvc-model-registry/1.0' })

	with urllib.request.urlopen(request, timeout = 10) as response:
		payload = response.read().decode('utf-8')
		return __import__('json').loads(payload)


def normalize_identifier(value : str) -> str:
	return re.sub(r'[^a-zA-Z0-9_]+', '_', value).strip('_').lower()
