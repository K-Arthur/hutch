"""SecretRef, principal and category contracts.

The parser is the place where a permissive implementation would let a value into something that
gets logged, so the negative cases matter more than the positive ones.
"""

from __future__ import annotations

import pytest

from hutch.vault import refs

SECRET_ID = "sec_" + "0123456789abcdef01234567"


def test_canonical_reference_round_trips():
    ref = refs.SecretRef.parse(f"secret://hutch/local/{SECRET_ID}")
    assert ref.provider == "hutch"
    assert ref.alias == "local"
    assert ref.secret_id == SECRET_ID
    assert ref.version is None
    assert ref.local is True
    assert str(ref) == f"secret://hutch/local/{SECRET_ID}"


def test_versioned_reference_round_trips():
    ref = refs.SecretRef.parse(f"secret://hutch/local/{SECRET_ID}#v3")
    assert ref.version == 3
    assert str(ref).endswith("#v3")


def test_local_ref_helper_matches_parser():
    built = refs.SecretRef.local_ref(SECRET_ID, version=2)
    assert refs.SecretRef.parse(str(built)) == built


@pytest.mark.parametrize("text", [
    "",
    SECRET_ID,                                             # bare id, not a reference
    f"secret://hutch/local/{SECRET_ID} ",                  # trailing space
    f" secret://hutch/local/{SECRET_ID}",                  # leading space
    f"SECRET://hutch/local/{SECRET_ID}",                   # scheme case
    f"secret://HUTCH/local/{SECRET_ID}",                   # provider case
    f"secret://vault/local/{SECRET_ID}",                   # unimplemented provider
    f"secret://hutch/LOCAL/{SECRET_ID}",                   # alias case
    f"secret://hutch/local/{SECRET_ID}#v0",                # version 0
    f"secret://hutch/local/{SECRET_ID}#v01",               # leading zero
    f"secret://hutch/local/{SECRET_ID}#1",                 # wrong version marker
    f"secret://hutch/local/{SECRET_ID}#v1#v2",             # two versions
    f"secret://hutch/local/{SECRET_ID}/extra",             # extra segment
    f"secret://hutch/local/../../etc/passwd",              # traversal
    f"secret://hutch/local/{SECRET_ID}?x=1",               # query
    "secret://hutch/local/" + "sec_" + "A" * 24,           # uppercase id
    "secret://hutch/local/" + "sec_" + "a" * 23,           # too short
    "secret://hutch/local/" + "sec_" + "a" * 25,           # too long
    "secret://hutch/local/sec_0123456789abcdef0123456",    # 23 hex
    "secret://" + "a" * 64 + "/local/" + SECRET_ID,        # alias too long
    "secret://hutch/local/" + SECRET_ID + "#v1234567890",  # version too long
])
def test_reference_parser_refuses_everything_else(text):
    with pytest.raises(refs.SecretRefError):
        refs.SecretRef.parse(text)


def test_reference_parser_refuses_non_text_and_overlong_input():
    with pytest.raises(refs.SecretRefError):
        refs.SecretRef.parse(None)
    with pytest.raises(refs.SecretRefError):
        refs.SecretRef.parse(123)
    with pytest.raises(refs.SecretRefError):
        refs.SecretRef.parse("secret://hutch/local/" + SECRET_ID + "x" * 200)


def test_reference_never_holds_a_value_field():
    """The dataclass must not grow a value-like field by accident."""
    assert set(refs.SecretRef.__dataclass_fields__) == {"provider", "alias", "secret_id", "version"}


def test_direct_construction_validates_each_part():
    with pytest.raises(refs.SecretRefError):
        refs.SecretRef(provider="bitwarden", alias="local", secret_id=SECRET_ID)
    with pytest.raises(refs.SecretRefError):
        refs.SecretRef(provider="hutch", alias="Local", secret_id=SECRET_ID)
    with pytest.raises(refs.SecretRefError):
        refs.SecretRef(provider="hutch", alias="local", secret_id="not-a-secret-id")
    with pytest.raises(refs.SecretRefError):
        refs.SecretRef(provider="hutch", alias="local", secret_id=SECRET_ID, version=0)
    with pytest.raises(refs.SecretRefError):
        refs.SecretRef(provider="hutch", alias="local", secret_id=SECRET_ID, version=True)


def test_new_secret_id_is_well_formed_and_unique():
    ids = {refs.new_secret_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(refs.SECRET_ID_PATTERN.fullmatch(value) for value in ids)


def test_parse_category_refuses_unknown_values():
    assert refs.parse_category("api_key") is refs.SecretCategory.API_KEY
    assert refs.parse_category(refs.SecretCategory.SSH_PRIVATE_KEY) is refs.SecretCategory.SSH_PRIVATE_KEY
    with pytest.raises(refs.SecretRefError):
        refs.parse_category("passwords")
    with pytest.raises(refs.SecretRefError):
        refs.parse_category(None)


def test_every_category_has_a_profile_with_a_positive_bound():
    for category in refs.SecretCategory:
        profile = refs.category_profile(category)
        assert profile.label
        assert profile.max_bytes >= 4096
        assert isinstance(profile.lifecycle, refs.Lifecycle)


def test_categories_distinguish_lifecycles():
    lifecycles = {refs.category_profile(c).lifecycle for c in refs.SecretCategory}
    assert refs.Lifecycle.ROTATING in lifecycles
    assert refs.Lifecycle.SHORT_LIVED in lifecycles
    assert refs.Lifecycle.PRIVATE_KEY in lifecycles
    assert refs.Lifecycle.OAUTH_MANAGED in lifecycles


@pytest.mark.parametrize("scope", ["workspace", "bot:bot_0123456789ab"])
def test_valid_scopes(scope):
    assert refs.parse_scope(scope) == scope


@pytest.mark.parametrize("scope", ["", "user:1", "bot:", "bot:0123456789ab", "bot:bot_xyz",
                                   "workspace ", "WORKSPACE", None])
def test_invalid_scopes(scope):
    with pytest.raises(refs.SecretRefError):
        refs.parse_scope(scope)


def test_owner_principal_canonicalises_identity():
    assert refs.Principal.owner().label == "owner"
    assert refs.Principal("owner").id == "owner"
    assert refs.Principal.owner().is_owner is True
    assert refs.Principal.bot("bot_0123456789ab").is_owner is False


@pytest.mark.parametrize("kind,value", [
    ("owner", "someone-else"),
    ("workspace", "tenant-2"),
    ("bot", "bot_short"),
    ("bot", ""),
    ("connector", "Bad Slug"),
    ("skill", "../escape"),
    ("nobody", "x"),
])
def test_principals_are_validated(kind, value):
    with pytest.raises(refs.SecretRefError):
        refs.Principal(kind, value)


def test_scope_allows_denies_cross_bot_access():
    alpha = refs.Principal.bot("bot_aaaaaaaaaaaa")
    beta = refs.Principal.bot("bot_bbbbbbbbbbbb")
    assert alpha.scope_allows("workspace") is True
    assert alpha.scope_allows("bot:bot_aaaaaaaaaaaa") is True
    assert alpha.scope_allows("bot:bot_bbbbbbbbbbbb") is False
    assert beta.scope_allows("bot:bot_aaaaaaaaaaaa") is False
    # A connector or skill never reaches a bot-scoped secret, even with a grant.
    assert refs.Principal("connector", "notion").scope_allows("bot:bot_aaaaaaaaaaaa") is False
    assert refs.Principal.workspace().scope_allows("bot:bot_aaaaaaaaaaaa") is False
    assert refs.Principal.workspace().scope_allows("workspace") is True


def test_delegable_permissions_exclude_owner_only_actions():
    assert refs.Permission.USE in refs.DELEGABLE_PERMISSIONS
    assert refs.Permission.REVEAL in refs.DELEGABLE_PERMISSIONS
    assert refs.Permission.ROTATE not in refs.DELEGABLE_PERMISSIONS
    assert refs.Permission.DELETE not in refs.DELEGABLE_PERMISSIONS


def test_names_and_descriptions_are_normalised_and_bounded():
    assert refs.clean_name("  Notion\tAPI   key ") == "Notion API key"
    with pytest.raises(refs.SecretRefError):
        refs.clean_name("   ")
    with pytest.raises(refs.SecretRefError):
        refs.clean_name("x" * (refs.MAX_NAME_CHARS + 1))
    with pytest.raises(refs.SecretRefError):
        refs.clean_name("bad\x00name")
    assert refs.clean_description(None) == ""
    assert refs.clean_description("  a   note ") == "a note"
    with pytest.raises(refs.SecretRefError):
        refs.clean_description("x" * (refs.MAX_DESCRIPTION_CHARS + 1))
