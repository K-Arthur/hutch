"""Public docs only link to files a fresh clone has.

"A fresh clone has it" means git tracks it. A link to an untracked or removed file works on the
author's machine and 404s for everyone else (the docs index still listed a `prompts/` directory
that had been archived off-repository).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]]*\]\(([^)\s]+)\)")
TOP_LEVEL = ("README.md", "AGENTS.md", "PRODUCT.md", "DESIGN.md", "SECURITY.md", "CONTRIBUTING.md")


def _tracked() -> set[str]:
    listing = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return {line for line in listing.split("\n") if line}


def _known(tracked: set[str]) -> set[str]:
    return tracked | {str(parent) for path in tracked for parent in Path(path).parents}


def _public_docs(tracked: set[str]) -> list[str]:
    docs = [path for path in tracked if re.fullmatch(r"docs/[^/]+\.md", path)]
    return sorted(set(p for p in TOP_LEVEL if p in tracked) | set(docs) | ({"docs/README.md"} & tracked))


def test_public_docs_link_only_to_tracked_files():
    tracked = _tracked()
    known = _known(tracked)
    docs = _public_docs(tracked)
    assert len(docs) > 20, "the scan should cover the public docs"
    broken = []
    for doc in docs:
        text = (ROOT / doc).read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = (match.group(1) or match.group(2)).split("#")[0].split("?")[0]
            if not target or re.match(r"[a-z]+:|//|mailto:", target):
                continue
            resolved = os.path.normpath(target.lstrip("/") if target.startswith("/") else (Path(doc).parent / target).as_posix())
            if resolved not in known:
                broken.append((doc, target))
    assert broken == [], f"links to files a fresh clone lacks: {broken[:10]}"


def test_readme_commands_name_scripts_that_exist():
    tracked = _tracked()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    named = set(re.findall(r"\b(scripts/[A-Za-z0-9_./-]+\.(?:py|sh))\b", readme))
    assert named, "the README names at least the responsive validation script"
    assert [n for n in sorted(named) if n not in tracked] == []
