"""Reviewed identity data: bounded, revision-checked, never applied when damaged.

The person's profile and each assistant's boundaries are JSON in the state directory (no migration, no
model tools). These tests pin the bounds, the revision CAS, file permissions, the advisory prompt block
and the damaged-file contract: a broken file is reported and contributes nothing to the prompt.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from hutch.identity import (
    MAX_BOUNDARY_CHARS,
    AssistantIdentity,
    IdentityConflict,
    PersonProfile,
    load_assistant_identity,
    load_person_profile,
    prompt_block,
    render_block,
    save_assistant_identity,
    save_person_profile,
)
from hutch.models import Bot, Run
from hutch.runtime.instructions import build_system_prompt


def test_bounds_are_enforced():
    with pytest.raises(ValidationError):
        AssistantIdentity(boundaries=["x"] * 9)
    with pytest.raises(ValidationError):
        AssistantIdentity(boundaries=["x" * (MAX_BOUNDARY_CHARS + 1)])
    with pytest.raises(ValidationError):
        AssistantIdentity(signature="x" * 401)
    with pytest.raises(ValidationError):
        PersonProfile(about="x" * 2001)
    with pytest.raises(ValidationError):
        PersonProfile(surprise="field")
    assert AssistantIdentity(boundaries=["  keep   it  tight ", "", "  "]).boundaries == ["keep it tight"]


def test_revision_is_a_compare_and_set(tmp_path):
    first = save_assistant_identity(tmp_path, "bot_1", AssistantIdentity())
    assert first.revision == 1
    second = save_assistant_identity(tmp_path, "bot_1", first)
    assert second.revision == 2
    with pytest.raises(IdentityConflict):
        save_assistant_identity(tmp_path, "bot_1", first)     # stale reviewer copy
    assert load_assistant_identity(tmp_path, "bot_1")[0].revision == 2


def test_saved_files_are_private_and_inside_the_state_directory(tmp_path):
    save_person_profile(tmp_path, PersonProfile(preferred_name="Kev"))
    save_assistant_identity(tmp_path, "bot_1", AssistantIdentity(signature="done"))
    for path in (tmp_path / "identity" / "person.json", tmp_path / "identity" / "assistant-bot_1.json"):
        assert path.parent == tmp_path / "identity"
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_a_damaged_file_is_a_diagnostic_not_an_applied_identity(tmp_path):
    directory = tmp_path / "identity"
    directory.mkdir()
    (directory / "assistant-bot_1.json").write_text("{not json", encoding="utf-8")
    (directory / "person.json").write_text('{"preferred_name": "x", "about": "y", "treat_person": "z", '
                                           '"surprise": 1}', encoding="utf-8")
    identity, identity_problem = load_assistant_identity(tmp_path, "bot_1")
    profile, profile_problem = load_person_profile(tmp_path)
    assert identity.revision == 0 and "could not be read" in identity_problem
    assert profile.preferred_name == "" and "could not be read" in profile_problem
    assert prompt_block(tmp_path, "bot_1") == ""      # nothing damaged is ever applied


def test_the_prompt_block_is_only_the_saved_text_and_is_advisory(tmp_path):
    save_assistant_identity(tmp_path, "bot_1", AssistantIdentity(
        signature="Done — reporting back.", boundaries=["Never send email without approval"]))
    save_person_profile(tmp_path, PersonProfile(preferred_name="Kev", about="Builds local-first tools."))
    block = prompt_block(tmp_path, "bot_1")
    assert "Kev" in block and "Never send email without approval" in block and "Done" in block
    assert "advisory context" in block and "tool policy still govern" in block
    assert render_block(AssistantIdentity(), PersonProfile()) == ""


def test_the_system_prompt_includes_the_saved_identity(tmp_path):
    bot = Bot(name="identity-check", model="ollama/llama3.2:3b", tools=[])
    save_assistant_identity(tmp_path, bot.id, AssistantIdentity(boundaries=["Never publish without review"]))
    save_person_profile(tmp_path, PersonProfile(preferred_name="Kev"))
    ctx = SimpleNamespace(bot=bot, run=Run(bot_id=bot.id, prompt="x"),
                          store=SimpleNamespace(workspace_coordinator_id=lambda: "someone-else"),
                          workspace=Path("/tmp/work"), dry_run=False, skills=None,
                          config=SimpleNamespace(state_dir=tmp_path))
    prompt = build_system_prompt(ctx)
    assert "Preferred name: Kev" in prompt and "Never publish without review" in prompt
    # Nothing saved: no empty heading and no extra prompt tokens.
    assert prompt_block(tmp_path / "fresh", "bot_2") == ""
