"""The sdist ships source, not 270 MB of evidence screenshots.

`docs/` is included whole because tests load JSON and Markdown fixtures from it, but its
screenshots (thousands of PNGs) are evidence, not inputs. A published sdist must stay small.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_build_excludes_binary_media_under_docs():
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    exclude = config["tool"]["hatch"]["build"]["exclude"]
    for pattern in ("/docs/**/*.png", "/docs/**/*.webp", "/docs/**/*.jpg", "/docs/**/*.webm", "/docs/**/*.mp4"):
        assert pattern in exclude, f"{pattern} would put evidence media into the sdist"


def test_sdist_still_includes_the_fixtures_tests_load_from_docs():
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    include = config["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert "/docs" in include and "/tests" in include
