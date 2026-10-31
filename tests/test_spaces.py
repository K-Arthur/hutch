"""Shared spaces: membership, per-assistant grants and scope isolation."""

from __future__ import annotations

import pytest

from hutch.models import Bot
from hutch.personal import Commitment, Space, SpaceMember, SpaceRole
from hutch.personal.store import PersonalStore


@pytest.fixture()
def personal(store):
    return PersonalStore(store)


def _space(personal, name="Maple household"):
    return personal.spaces.create(Space(name=name, kind="household"))


def test_membership_roles_and_last_owner_protection(personal):
    space = _space(personal)
    owner = personal.spaces.add_member(space.id, SpaceMember(display_name="Kevin", role=SpaceRole.owner))
    partner = personal.spaces.add_member(space.id, SpaceMember(display_name="Sam", role=SpaceRole.adult))
    assert [m.display_name for m in personal.spaces.members(space.id)] == ["Kevin", "Sam"]
    with pytest.raises(ValueError):
        personal.spaces.update_member(space.id, owner.member_id, {"status": "revoked"})
    personal.spaces.add_member(space.id, SpaceMember(display_name="Alex", role=SpaceRole.owner))
    revoked = personal.spaces.revoke_member(space.id, owner.member_id)
    assert revoked.status.value == "revoked"
    assert [m.display_name for m in personal.spaces.members(space.id, include_revoked=False)] == ["Alex", "Sam"]
    with pytest.raises(ValueError):
        personal.spaces.add_member(space.id, SpaceMember(member_id="mem_active", display_name="Sam",
                                                        role=SpaceRole.adult))
        personal.spaces.add_member(space.id, SpaceMember(member_id="mem_active", display_name="Sam",
                                                        role=SpaceRole.adult))


def test_bot_visibility_is_personal_plus_only_granted_spaces(personal, store):
    bot = store.create_bot(Bot(name="household-bot"))
    other = store.create_bot(Bot(name="private-bot"))
    space = _space(personal)
    other_space = _space(personal, "Beach project")
    personal.commitments.create(Commitment(title="Personal item"), actor="owner")
    shared, _ = personal.commitments.create(Commitment(title="Shared item", space_id=space.id), actor="owner")
    personal.commitments.create(Commitment(title="Other project item", space_id=other_space.id), actor="owner")

    personal.spaces.grant(space.id, bot.id)
    assert [item.title for item in personal.bot_visible_commitments(bot)] == ["Personal item", "Shared item"]
    assert [item.title for item in personal.bot_visible_commitments(other)] == ["Personal item"]
    assert personal.spaces.bot_can_access(bot.id, space.id)
    assert not personal.spaces.bot_can_access(bot.id, other_space.id)

    personal.spaces.revoke_grant(space.id, bot.id)
    assert [item.title for item in personal.bot_visible_commitments(bot)] == ["Personal item"]
    assert not personal.spaces.bot_can_access(bot.id, space.id)


def test_archiving_revokes_assistant_access_but_keeps_history(personal, store):
    bot = store.create_bot(Bot(name="archive-bot"))
    space = _space(personal)
    personal.spaces.add_member(space.id, SpaceMember(display_name="Kevin", role=SpaceRole.owner))
    personal.spaces.grant(space.id, bot.id)
    shared, _ = personal.commitments.create(Commitment(title="Shared item", space_id=space.id), actor="owner")
    personal.spaces.archive(space.id, expected_revision=1)
    assert personal.spaces.bot_space_ids(bot.id) == set()
    assert personal.spaces.get(space.id).archived is True
    assert personal.commitments.get(shared.id) is not None  # history is not destroyed
    summary = personal.spaces.summary()
    assert all(item["archived"] is True for item in summary)


def test_space_edit_rejects_a_stale_revision(personal):
    space = _space(personal)
    updated = personal.spaces.update(space.id, {"name": "Maple home"}, expected_revision=1)
    assert updated.revision == 2
    with pytest.raises(Exception):
        personal.spaces.update(space.id, {"name": "Stale"}, expected_revision=1)
