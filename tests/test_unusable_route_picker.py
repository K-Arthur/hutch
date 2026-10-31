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
