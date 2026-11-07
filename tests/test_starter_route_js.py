"""The route a new person starts with: most private first, free hosted last, always disclosed.

`starter-route.js` is a pure function over two reads the browser already makes, shared by first run, the
new-assistant setup and the Models page. These tests run the real file under Node, with no browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parent.parent / "src" / "hutch" / "server" / "static" / "starter-route.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

SCRIPT = """
const fs = require('fs');
const window = {};                      // the file is a plain browser script: it publishes on window
require('vm').runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), { window });
const starter = window.hutchStarterRoute;
const { openCode, routes } = JSON.parse(fs.readFileSync(0, 'utf8'));
const choice = starter.choose(openCode, routes);
process.stdout.write(JSON.stringify({ choice, disclosure: starter.disclosure(choice), html: starter.noticeHtml(choice) }));
"""


def pick(open_code=None, routes=None):
    done = subprocess.run(["node", "-e", SCRIPT, str(MODULE)], input=json.dumps({"openCode": open_code, "routes": routes or []}),
                          capture_output=True, text=True, timeout=30, check=True)
    return json.loads(done.stdout)


def model(spec, name="", context=0, capabilities=()):
    return {"spec": spec, "provider_id": "opencode", "model_id": spec.split("/")[-1], "name": name or spec.split("/")[-1],
            "context": context, "output": 0, "capabilities": list(capabilities)}


def opencode(models, authenticated=False):
    return {"ready": bool(models), "authenticated": authenticated, "models": models, "integrations": []}


def route(spec, *, hosted, state="ready", group=""):
    return {"spec": spec, "label": spec.split("/")[-1], "group": group, "state": state, "hosted": hosted}


def test_a_ready_model_on_this_computer_beats_everything():
    result = pick(opencode([model("opencode/opencode/a-free")]),
                  [route("ollama/llama3.2:3b", hosted=False, group="On this machine"), route("openai/gpt", hosted=True)])
    assert result["choice"]["model"] == "ollama/llama3.2:3b" and result["choice"]["hosted"] is False
    assert result["disclosure"] is None and result["html"] == ""


def test_a_provider_the_person_connected_beats_a_free_hosted_model():
    result = pick(opencode([model("opencode/opencode/a-free")]), [route("openai/gpt-4o-mini", hosted=True, group="OpenAI")])
    assert result["choice"]["model"] == "openai/gpt-4o-mini" and result["choice"]["hosted"] is True
    assert result["disclosure"]["kind"] == "account" and "may cost money" in result["disclosure"]["body"]


def test_routes_that_are_not_ready_are_never_chosen():
    result = pick(None, [route("ollama/huge", hosted=False, state="wont_fit"), route("openai/gpt", hosted=True, state="setup")])
    assert result["choice"] is None and result["html"] == ""


def test_an_unconnected_opencode_profile_is_all_free_and_prefers_tools_then_room():
    models = [model("opencode/opencode/plain", context=200_000),
              model("opencode/opencode/small-tools", context=32_000, capabilities=["toolcall"]),
              model("opencode/opencode/big-tools", context=128_000, capabilities=["toolcall", "reasoning"])]
    result = pick(opencode(models))
    assert result["choice"]["model"] == "opencode/opencode/big-tools"
    assert result["choice"]["kind"] == "opencode" and result["choice"]["runtime"] == "opencode" and result["choice"]["free"] is True
    assert result["choice"]["count"] == 3


def test_ties_keep_opencodes_own_order():
    result = pick(opencode([model("opencode/opencode/first"), model("opencode/opencode/second")]))
    assert result["choice"]["model"] == "opencode/opencode/first"


def test_a_free_start_always_carries_the_notice_and_says_where_to_change_it():
    result = pick(opencode([model("opencode/opencode/deepseek-free")]))
    note = result["disclosure"]
    assert note["kind"] == "free" and "hosted by OpenCode" in note["title"]
    assert "leaves this computer" in note["body"] and "keep or learn from it" in note["body"]
    assert "Settings" in note["change"] and "AI model tab" in note["change"]
    assert 'role="note"' in result["html"] and 'data-kind="free"' in result["html"]


def test_once_connected_only_models_named_free_count_as_a_free_start():
    models = [model("opencode/anthropic/claude-big", context=1_000_000, capabilities=["toolcall"]),
              model("opencode/opencode/glm-flash-free", context=64_000)]
    result = pick(opencode(models, authenticated=True))
    assert result["choice"]["model"] == "opencode/opencode/glm-flash-free" and result["choice"]["free"] is True


def test_a_connected_profile_with_no_free_model_is_offered_as_the_persons_own_account():
    result = pick(opencode([model("opencode/anthropic/claude-big", capabilities=["toolcall"])], authenticated=True))
    assert result["choice"]["model"] == "opencode/anthropic/claude-big" and result["choice"]["free"] is False
    assert result["disclosure"]["kind"] == "account"


@pytest.mark.parametrize("status", [None, {}, {"ready": False, "models": [model("opencode/opencode/x")]}, {"ready": True, "models": []},
                                    {"ready": True, "models": [{"name": "no spec"}]}])
def test_nothing_ready_means_no_starter_and_no_notice(status):
    result = pick(status)
    assert result["choice"] is None and result["disclosure"] is None and result["html"] == ""


AVAILABILITY = """
const fs = require('fs');
const window = {};
require('vm').runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), { window });
const choice = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(window.hutchStarterRoute.availability(choice)));
"""


def sentence(choice):
    done = subprocess.run(["node", "-e", AVAILABILITY, str(MODULE)], input=json.dumps(choice),
                          capture_output=True, text=True, timeout=30, check=True)
    return json.loads(done.stdout)


def test_the_availability_sentence_says_what_exists_and_that_nothing_is_saved():
    one = sentence(pick(opencode([model("opencode/opencode/a-free")]))["choice"])
    many = sentence(pick(opencode([model("opencode/opencode/a-free"), model("opencode/opencode/b-free")]))["choice"])
    assert one.startswith("OpenCode is available with 1 model option.") and "1 model options" not in one
    assert many.startswith("OpenCode is available with 2 model options.")
    assert "without a separate account" in one
    assert one.endswith("None is saved as the default for new assistants yet.")
    assert "ready" not in one.lower()                       # "ready" read as saved next to "No default route"


def test_a_connected_account_and_an_own_provider_route_use_the_same_closing_claim():
    connected = sentence(pick(opencode([model("opencode/opencode/a-free")], authenticated=True))["choice"])
    own = sentence(pick(None, [route("deepseek/deepseek-chat", hosted=True, group="DeepSeek")])["choice"])
    assert "A provider account is connected." in connected and connected.endswith("yet.")
    assert own.startswith("DeepSeek has a model route you can use.") and own.endswith("None is saved as the default for new assistants yet.")


def test_no_choice_yields_no_sentence():
    assert sentence(None) == ""
