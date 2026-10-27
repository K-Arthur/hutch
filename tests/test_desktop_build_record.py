"""Package evidence must identify actual files and disclose incomplete metadata."""
import hashlib
from types import SimpleNamespace

import pytest

from scripts.record_desktop_build import artifacts, python_inventory


def test_desktop_manifest_hashes_both_actual_package_files_and_refuses_duplicates(tmp_path):
    for kind, name, content in [('deb', 'Hutch.deb', b'deb fixture'),
                                ('appimage', 'Hutch.AppImage', b'image fixture')]:
        directory = tmp_path / kind
        directory.mkdir()
        (directory / name).write_bytes(content)
    result = artifacts(tmp_path)
    assert result[0]['sha256'] == hashlib.sha256(b'deb fixture').hexdigest()
    assert result[1]['bytes'] == len(b'image fixture')
    (tmp_path / 'deb' / 'unexpected.deb').write_bytes(b'other')
    with pytest.raises(ValueError, match='exactly one deb'):
        artifacts(tmp_path)


def test_desktop_manifest_refuses_symlinked_packages_and_missing_formats(tmp_path):
    (tmp_path / 'deb').mkdir()
    original = tmp_path / 'not-a-package'
    original.write_bytes(b'fixture')
    link = tmp_path / 'deb' / 'Hutch.deb'
    try:
        link.symlink_to(original)
    except OSError:
        pytest.skip('this host cannot create a symlink')
    with pytest.raises(ValueError, match='regular files'):
        artifacts(tmp_path)
    link.unlink()
    link.write_bytes(b'deb')
    with pytest.raises(ValueError, match='exactly one appimage'):
        artifacts(tmp_path)


def test_dependency_inventory_discloses_missing_and_truncated_license_metadata(monkeypatch):
    from email.message import Message
    missing, long = Message(), Message()
    missing['Name'], missing['Version'] = 'unknown-license', '1'
    long['Name'], long['Version'] = 'long-license', '2'
    long['License-Expression'], long['License'] = 'MIT', 'x' * 3000
    monkeypatch.setattr('scripts.record_desktop_build.metadata.distributions', lambda: [
        SimpleNamespace(metadata=missing, version='1'), SimpleNamespace(metadata=long, version='2')])
    rows = python_inventory()
    assert rows[0]['review_required'] and rows[0]['license_metadata_truncated']
    assert rows[0]['license_metadata_sha256'] == hashlib.sha256(('x' * 3000).encode()).hexdigest()
    assert rows[1]['review_required'] and rows[1]['license_expression'] is None
