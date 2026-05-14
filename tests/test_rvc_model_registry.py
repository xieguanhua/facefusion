from facefusion import rvc_model_registry


def test_load_default_entries() -> None:
	entries = rvc_model_registry.load_default_entries()

	assert entries
	assert all(entry.get('id') for entry in entries)
	assert all(entry.get('model_url').startswith('https://') for entry in entries)


def test_filter_and_parse_entry_choice() -> None:
	entries =\
	[
		{
			'id': 'hf_one',
			'name': 'One',
			'source': 'huggingface',
			'model_url': 'https://huggingface.co/a/b',
			'index_url': ''
		},
		{
			'id': 'gh_two',
			'name': 'Two',
			'source': 'github',
			'model_url': 'https://github.com/a/b',
			'index_url': ''
		}
	]
	huggingface_entries = rvc_model_registry.filter_entries(entries, 'huggingface')
	github_entries = rvc_model_registry.filter_entries(entries, 'github')

	assert len(huggingface_entries) == 1
	assert len(github_entries) == 1
	choice = rvc_model_registry.format_entry_choice(huggingface_entries[0])
	assert rvc_model_registry.parse_entry_id(choice) == 'hf_one'
