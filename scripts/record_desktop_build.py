"""Record unsigned Linux package identity and resolved dependency metadata.

This inventory is build evidence, not a claim that native-library licenses,
exact frozen contents or release readiness have been reviewed.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def artifacts(bundle: Path) -> list[dict]:
    root = bundle.resolve(strict=True)
    result = []
    for kind, suffix in (('deb', '.deb'), ('appimage', '.AppImage')):
        candidates = sorted((root / kind).glob('*' + suffix))
        if len(candidates) != 1:
            raise ValueError(f'expected exactly one {kind} artifact')
        path = candidates[0]
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('package artifacts must be regular files inside the bundle root')
        result.append({'file': str(path.relative_to(root)), 'bytes': path.stat().st_size,
                       'sha256': sha256(path), 'signature': 'unsigned'})
    return result


def python_inventory() -> list[dict]:
    result = []
    for distribution in metadata.distributions():
        meta = distribution.metadata
        raw = meta.get('License') or ''
        expression = meta.get('License-Expression')
        result.append({'name': meta['Name'], 'version': distribution.version,
            'license_expression': expression,
            'license_classifiers': [item for item in meta.get_all('Classifier', []) if item.startswith('License ::')],
            'license_metadata': raw[:2048], 'license_metadata_truncated': len(raw) > 2048,
            'license_metadata_sha256': hashlib.sha256(raw.encode()).hexdigest() if raw else None,
            'review_required': not bool(expression) or len(raw) > 2048})
    return sorted(result, key=lambda item: (item['name'].casefold(), item['version']))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    packages = artifacts(args.bundle)
    cargo = subprocess.run(['cargo', 'metadata', '--locked', '--offline', '--filter-platform',
        'x86_64-unknown-linux-gnu', '--manifest-path', str(root / 'desktop/Cargo.toml'),
        '--format-version', '1'], check=True, capture_output=True, text=True, timeout=120)
    rust = [{'name': item['name'], 'version': item['version'], 'license_expression': item['license'],
             'review_required': not bool(item['license'])} for item in json.loads(cargo.stdout)['packages']]
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    record = {'contract_version': 1, 'source_commit': revision, 'packages': packages,
        'python': platform.python_version(), 'system': platform.platform(),
        'python_dependencies': python_inventory(), 'rust_dependencies': rust,
        'inventory_scope': 'Installed build Python distributions and resolved Linux Rust dependency graph, including build/test dependencies; not an exact binary SBOM.',
        'release_ready': False,
        'remaining_license_review': 'Check exact PyInstaller/native-library payload and bundled license files; resolve missing/truncated metadata before publication.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
