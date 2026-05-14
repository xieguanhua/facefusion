from facefusion.uis.components.webcam_options import resolve_stream_target


def test_resolve_stream_target() -> None:
	assert resolve_stream_target('inline') == 'inline preview only'
	assert resolve_stream_target('udp') == 'udp://localhost:27000?pkt_size=1316'
	assert resolve_stream_target('v4l2')
