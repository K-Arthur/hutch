"""The model picker offers only models that can answer (owner report: "it still shows demo models")."""

from __future__ import annotations

import pytest

from hutch.modelchoices import model_choices
from tests.test_model_switcher import env, mkbot  # noqa: F401  (the picker's own fixtures)


@pytest.mark.parametrize("saved", ["", "demo", "mock/demo", "no-slash"])
def test_a_route_that_cannot_run_is_not_offered_as_the_assistants_default(env, saved):
    """The picker lists only models that can answer; an unusable saved route is the chip's "Choose a model", not a row."""
    bot = mkbot(env, model=saved)
    choices = model_choices(env.config, env.store, bot)
    assert not any(choice.default for choice in choices), saved
    assert saved not in {choice.spec for choice in choices if choice.spec}, saved


def test_a_working_route_is_still_the_default_the_picker_leads_with(env):
    bot = mkbot(env, model="ollama/llama3.2:3b")
    first = model_choices(env.config, env.store, bot)[0]
    assert first.spec == "ollama/llama3.2:3b" and first.default is True


def _opencode_fixture(monkeypatch):
    from hutch import modelchoices
    from hutch.modelchoices import Choice
    ready = [Choice(spec="opencode/opencode/glm-flash-free", label="glm-flash-free", group="OpenCode · opencode", state="ready",
                    hosted=True, runtime="opencode", note="OpenCode-managed account")]
    monkeypatch.setattr(modelchoices, "_opencode_choices", lambda config, bot: list(ready))


@pytest.mark.parametrize("saved", ["mock/demo", "", "ollama/llama3.2:3b"])
def test_the_picker_lists_opencode_models_for_an_assistant_on_the_builtin_runtime(env, monkeypatch, saved):
    """Owner report: with OpenCode installed the picker showed only hosted models that all said "needs setup"."""
    _opencode_fixture(monkeypatch)
    bot = mkbot(env, model=saved)
    listed = {choice.spec: choice for choice in model_choices(env.config, env.store, bot, any_runtime=True)}
    assert listed["opencode/opencode/glm-flash-free"].state == "ready"
    assert listed["opencode/opencode/glm-flash-free"].runtime == "opencode", "the picker needs to know choosing it switches runtime"


def test_opencode_models_are_not_added_to_the_builtin_setup_list_unless_asked(env, monkeypatch):
    """First run composes its own decision from the builtin list; OpenCode routes must not leak into it."""
    _opencode_fixture(monkeypatch)
    bot = mkbot(env, model="")
    assert "opencode/opencode/glm-flash-free" not in {choice.spec for choice in model_choices(env.config, env.store, bot)}


def test_a_local_only_assistant_is_never_offered_a_hosted_opencode_model(env, monkeypatch):
    from hutch.models import InferenceMode
    _opencode_fixture(monkeypatch)
    bot = mkbot(env, model="ollama/llama3.2:3b", inference_mode=InferenceMode.local)
    assert "opencode/opencode/glm-flash-free" not in {choice.spec for choice in model_choices(env.config, env.store, bot, any_runtime=True)}


@pytest.mark.parametrize("spec,label", [("opencode/opencode/nemotron-3.5-super-vl-free", "nemotron-3.5-super-vl-free"),
                                        ("ollama/llama3.2:3b", "llama3.2:3b"), ("openai/gpt-4o", "gpt-4o")])
def test_model_labels_name_the_model_not_the_route(spec, label):
    from hutch.modelchoices import short_label
    assert short_label(spec) == label


def test_a_hosted_model_that_needs_a_key_says_where_to_add_it(env, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    bot = mkbot(env, model="ollama/llama3.2:3b")
    hosted = [c for c in model_choices(env.config, env.store, bot) if c.spec.startswith("anthropic/")]
    assert hosted and all("Apps & AI" in c.fix for c in hosted), "an environment variable alone is no way to add a provider"
