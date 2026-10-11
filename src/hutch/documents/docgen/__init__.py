"""Typed content specification → deterministic document bytes.

The model drafts structured content; these modules render it. Nothing here executes
content, fetches network resources, or trusts model-authored paths. A format module
registers itself with ``@register("fmt")``; ``generate`` dispatches and never falls back
to a weaker format silently — an unsupported format is an error, not a disguised text file.

Generation and validation are one gate: ``generate`` returns bytes only after the
format's own parse-back checks pass, and every result carries the validation state and
findings that the UI reports. A failed gate raises ``DocumentGenerationError`` and
nothing is promoted to storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..storage import DOCUMENT_FORMATS


class DocumentGenerationError(ValueError):
    """The content specification could not be rendered and validated; nothing was stored."""


@dataclass
class GeneratedDocument:
    data: bytes
    generator: str
    validation_state: str                 # "passed" | "passed_with_warnings"
    findings: list[dict[str, Any]] = field(default_factory=list)
    preview_mode: str = "structure"       # "pages" | "structure" | "download_only"
    preview_data: dict[str, Any] = field(default_factory=dict)
    page_count: int | None = None


_GENERATORS: dict[str, Callable[[dict[str, Any]], GeneratedDocument]] = {}


def register(fmt: str) -> Callable:
    if fmt not in DOCUMENT_FORMATS:
        raise ValueError(f"unknown document format: {fmt}")
    def wrap(fn: Callable[[dict[str, Any]], GeneratedDocument]) -> Callable:
        _GENERATORS[fmt] = fn
        return fn
    return wrap


def supported_formats() -> list[str]:
    return sorted(_GENERATORS)


def generate(fmt: str, spec: dict[str, Any]) -> GeneratedDocument:
    fn = _GENERATORS.get(fmt)
    if fn is None:
        raise DocumentGenerationError(
            f"unsupported document format: {fmt} (supported: {', '.join(supported_formats())})")
    if not isinstance(spec, dict):
        raise DocumentGenerationError("the content specification must be an object")
    return fn(spec)


#: office layout rendering is registered separately when its optional dependencies exist
RENDERERS: dict[str, "Any"] = {}


def _load_builtin_generators() -> None:
    from . import texty  # noqa: F401  (registers txt/md/csv/json/yaml)
    from . import docxgen  # noqa: F401  (registers docx)
    from . import pdfdoc  # noqa: F401  (registers pdf)
    from . import pptx  # noqa: F401  (registers pptx)
    from . import xlsx  # noqa: F401  (registers xlsx)


_load_builtin_generators()
