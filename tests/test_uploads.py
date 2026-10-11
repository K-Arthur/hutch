"""Upload intake: bounded files into a conversation's workspace, disclosed CSVs.

Covers the S2 slice end to end at the route level — the composer UI's journey is
pinned by the browser suite — plus the bounded CSV probe that both the report
route and the workspace kernel's ``inspect_csv`` helper share. Honesty rules
under test: nothing binary passes as text, nothing oversized passes, a tampered
file is a 410 rather than a plausible substitute, malformed CSV rows are
reported with line numbers instead of dropped, and delete is listing-level
bookkeeping, not an unlink.
"""

from __future__ import annotations

import hashlib
import os

import pytest
from fastapi.testclient import TestClient

from hutch.config import get_config
from hutch.server.app import create_app
from hutch.server.uploads import sanitize_upload_name
from hutch.workspace import csvprobe
from hutch.workspace.manager import workspace_dir_for


@pytest.fixture()
def api_client(config):
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture()
def conversation(api_client):
    bot = api_client.post("/api/bots", json={"name": "uploads-lane", "model": "mock/demo", "tools": []}).json()
    conversation, _ = api_client.app.state.store.create_conversation(
        bot["id"], "Upload lane", idem_key="uploads-lane", request_hash="uploads-lane")
    return conversation["id"]


def _upload(client, conversation_id, name: str, data: bytes):
    return client.post(
        f"/api/v1/conversations/{conversation_id}/uploads",
        files={"file": (name, data, "application/octet-stream")})


# ----------------------------------------------------------------- csvprobe

def test_probe_reports_columns_dupes_leading_zeros_and_timezones(tmp_path):
    path = tmp_path / "readings.csv"
    path.write_text(
        "id,account,when,region\n"
        "001,0123,2026-01-02T03:04:05+02:00,eu\n"
        "002,0456,2026-01-03T09:00:00Z,us\n",
        encoding="utf-8")
    report = csvprobe.probe_csv_path(path)
    assert report["header_present"] is True
    assert report["delimiter"] == ","
    assert report["rows_scanned"] == 3 and report["truncated_sample"] is False  # header + 2 data rows
    assert report["malformed_rows"] == {"count": 0, "first_line_numbers": []}
    by_name = {c["name"]: c for c in report["columns"]}
    assert by_name["account"]["leading_zeros"] == 2
    assert by_name["when"]["tz_like"] == 2
    assert report["duplicate_columns"] == []


def test_probe_reports_duplicate_columns_and_malformed_rows_with_line_numbers(tmp_path):
    path = tmp_path / "messy.csv"
    path.write_text(
        "a,a,b\n"
        "1,2,3\n"
        "4,5\n"            # line 3: one field short
        "6,7,8,9\n"        # line 4: one field over
        "10,11,12\n",
        encoding="utf-8")
    report = csvprobe.probe_csv_path(path)
    assert report["duplicate_columns"] == ["a"]
    assert report["malformed_rows"]["count"] == 2
    assert report["malformed_rows"]["first_line_numbers"] == [3, 4]
    assert report["expected_field_count"] == 3


def test_probe_discloses_quoted_newlines_encoding_fallback_and_truncation(tmp_path):
    path = tmp_path / "quoted.csv"
    path.write_bytes(
        b"name,note\n"
        b'"Smith, John","line one\nline two"\n'
        b"Jane,ok\n"
        + b"\xe9crit,oui\n")  # Latin-1 tail after a UTF-8 prefix
    report = csvprobe.probe_csv_path(path)
    assert report["quoted_newline_records"] == 1
    assert report["encoding"] == "latin-1"
    assert any("Latin-1" in note for note in report["notes"])
    small = csvprobe.probe_csv_path(path, sample_bytes=32)
    assert small["truncated_sample"] is True


def test_probe_reports_a_utf8_bom_instead_of_straying(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes(b"\xef\xbb\xbfcol1,col2\r\na,b\r\n")
    report = csvprobe.probe_csv_path(path)
    assert report["encoding"] == "utf-8-sig"
    assert [c["name"] for c in report["columns"]] == ["col1", "col2"]


def test_probe_header_inference_is_labeled_not_invented(tmp_path):
    path = tmp_path / "headerless.csv"
    path.write_text("1,2\n3,4\n", encoding="utf-8")
    report = csvprobe.probe_csv_path(path)
    assert report["header_present"] is False
    assert "data, not a header" in " ".join(report["notes"])
    assert [c["name"] for c in report["columns"]] == ["column_1", "column_2"]
    single = tmp_path / "single.csv"
    single.write_text("only-one-row\n", encoding="utf-8")
    one = csvprobe.probe_csv_path(single)
    assert one["header_present"] is None


# ------------------------------------------------------------------- routes

def test_upload_lands_in_workspace_hash_verified_and_serves_back(api_client, conversation, config):
    data = "col1,col2\n1,2\n".encode("utf-8")
    res = _upload(api_client, conversation, "readings.csv", data)
    assert res.status_code == 200, res.text
    row = res.json()
    assert row["filename"] == "readings.csv" and row["mime"] == "text/csv"
    assert row["sha256"] == hashlib.sha256(data).hexdigest()
    assert row["workspace_filename"].startswith(row["id"] + "-")
    stored = workspace_dir_for(config.state_dir, conversation) / row["workspace_filename"]
    assert stored.is_file() and stored.read_bytes() == data
    assert (os.lstat(stored).st_mode & 0o777) == 0o400

    served = api_client.get(f"/api/v1/conversations/{conversation}/uploads/{row['id']}/content")
    assert served.status_code == 200
    assert served.content == data
    assert served.headers["x-hutch-upload-verified"] == "sha256"
    assert served.headers["etag"] == f'"{row["sha256"]}"'
    cached = api_client.get(f"/api/v1/conversations/{conversation}/uploads/{row['id']}/content",
                            headers={"If-None-Match": f'"{row["sha256"]}"'})
    assert cached.status_code == 304


def test_upload_report_discloses_the_csv_instead_of_guessing(api_client, conversation):
    res = _upload(api_client, conversation, "messy.csv", "a,a\n1,2\n3\n".encode("utf-8"))
    row = res.json()
    report = api_client.get(f"/api/v1/conversations/{conversation}/uploads/{row['id']}/report").json()
    assert report["kind"] == "delimited-text"
    assert report["duplicate_columns"] == ["a"]
    assert report["malformed_rows"]["count"] == 1
    assert report["header_present"] is True


def test_upload_report_for_image_and_binary_refusals(api_client, conversation):
    png = (b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    row = _upload(api_client, conversation, "tiny.png", png).json()
    assert row["mime"] == "image/png"
    report = api_client.get(f"/api/v1/conversations/{conversation}/uploads/{row['id']}/report").json()
    assert report["kind"] == "image"

    binary = _upload(api_client, conversation, "looks-text.csv", b"col\x00umn\n1\x002\n")
    assert binary.status_code == 415
    disguised = _upload(api_client, conversation, "actually-png.csv", png)
    assert disguised.status_code == 415


def test_upload_bounds_oversize_unknown_conversation_and_delete(api_client, conversation):
    assert _upload(api_client, "nope", "x.csv", b"a\n").status_code == 404
    oversize = _upload(api_client, conversation, "big.csv", b"a,b\n" + b"1,2\n" * 1 + b"x" * (25_000_000))
    assert oversize.status_code == 413
    row = _upload(api_client, conversation, "gone.csv", b"a\n1\n").json()
    deleted = api_client.delete(f"/api/v1/conversations/{conversation}/uploads/{row['id']}")
    assert deleted.status_code == 200 and deleted.json()["state"] == "deleted"
    assert api_client.get(f"/api/v1/conversations/{conversation}/uploads/{row['id']}/content").status_code == 404
    listing = api_client.get(f"/api/v1/conversations/{conversation}/uploads").json()["uploads"]
    assert all(up["id"] != row["id"] for up in listing)


def test_tampered_workspace_file_is_gone_not_served(api_client, conversation):
    data = b"col\n1\n"
    row = _upload(api_client, conversation, "trusted.csv", data).json()
    stored = workspace_dir_for(get_config().state_dir, conversation) / row["workspace_filename"]
    stored.chmod(0o600)
    stored.write_bytes(b"col\n999\n")
    res = api_client.get(f"/api/v1/conversations/{conversation}/uploads/{row['id']}/content")
    assert res.status_code == 410
    report = api_client.get(f"/api/v1/conversations/{conversation}/uploads/{row['id']}/report")
    assert report.status_code == 410


def test_upload_names_are_sanitized_and_display_names_survive(api_client, conversation):
    res = _upload(api_client, conversation, "../evil name%.csv", b"a\n1\n")
    assert res.status_code == 200
    row = res.json()
    assert "/" not in row["workspace_filename"] and ".." not in row["workspace_filename"]
    assert row["filename"] == sanitize_upload_name("../evil name%.csv")
    second = _upload(api_client, conversation, "same-name.csv", b"a\n2\n").json()
    assert second["id"] != row["id"]
    assert second["workspace_filename"] != row["workspace_filename"]
