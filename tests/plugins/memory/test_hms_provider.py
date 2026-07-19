import json
from unittest.mock import patch

from plugins.memory import load_memory_provider
from plugins.memory.hms import HMSMemoryProvider, register


class Response:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.data).encode()


def test_provider_discovery_and_profile_scoped_read(monkeypatch):
    monkeypatch.setenv("HMS_BASE_URL", "http://hms.local/")
    monkeypatch.setenv("HMS_TIMEOUT_S", "1.25")
    provider = load_memory_provider("hms")
    assert isinstance(provider, HMSMemoryProvider)
    provider.initialize("session", agent_identity="profile one")

    with patch("urllib.request.urlopen", return_value=Response({"text": " curated memory "})) as urlopen:
        assert provider.system_prompt_block() == "curated memory"

    assert urlopen.call_args.args[0] == "http://hms.local/memories/blocks/context?profile=profile+one"
    assert urlopen.call_args.kwargs["timeout"] == 1.25


def test_current_aliases_toggle_and_fail_soft(monkeypatch):
    monkeypatch.delenv("HMS_BASE_URL", raising=False)
    monkeypatch.delenv("HMS_TIMEOUT_S", raising=False)
    monkeypatch.setenv("HERMES_HMS_URL", "http://legacy-hms:9000/")
    monkeypatch.setenv("HERMES_HMS_TIMEOUT", "3.5")
    provider = HMSMemoryProvider()
    provider.initialize("session", agent_identity="library")

    with patch("urllib.request.urlopen", return_value=Response({"text": "memory"})) as urlopen:
        assert provider.system_prompt_block() == "memory"
    assert urlopen.call_args.kwargs["timeout"] == 3.5

    monkeypatch.setenv("HERMES_MEMORY_BLOCKS_READ", "off")
    with patch("urllib.request.urlopen") as urlopen:
        assert provider.system_prompt_block() == ""
    urlopen.assert_not_called()

    monkeypatch.delenv("HERMES_MEMORY_BLOCKS_READ", raising=False)
    for response in (Response({}, 500), Response({"text": ""})):
        with patch("urllib.request.urlopen", return_value=response):
            assert provider.system_prompt_block() == ""
    with patch("urllib.request.urlopen", side_effect=OSError("down")):
        assert provider.system_prompt_block() == ""
    invalid_json = Response(None)
    invalid_json.read = lambda: b"not json"
    with patch("urllib.request.urlopen", return_value=invalid_json):
        assert provider.system_prompt_block() == ""


def test_registers_read_only_provider():
    class Context:
        provider = None

        def register_memory_provider(self, provider):
            self.provider = provider

    ctx = Context()
    register(ctx)

    assert isinstance(ctx.provider, HMSMemoryProvider)
    assert ctx.provider.name == "hms"
    assert ctx.provider.get_tool_schemas() == []
