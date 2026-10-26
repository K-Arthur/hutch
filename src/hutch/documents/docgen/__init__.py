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
from importlib import import_module
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
_BUILTINS = {
    **{fmt: 'texty' for fmt in ('txt', 'md', 'csv', 'json', 'yaml')},
    'docx': 'docxgen', 'xlsx': 'xlsx', 'pptx': 'pptx', 'zip': 'bundle', 'pdf': 'pdfdoc',
}


def register(fmt: str) -> Callable:
    if fmt not in DOCUMENT_FORMATS:
        raise ValueError(f"unknown document format: {fmt}")
    def wrap(fn: Callable[[dict[str, Any]], GeneratedDocument]) -> Callable:
        _GENERATORS[fmt] = fn
        return fn
    return wrap


def supported_formats() -> list[str]:
    """Implemented formats; native dependency availability is reported separately."""
    return sorted(set(_BUILTINS) | set(_GENERATORS))


def _generator(fmt: str):
    if fmt not in _GENERATORS and fmt in _BUILTINS:
        try:
            import_module(f'.{_BUILTINS[fmt]}', __name__)
        except (ImportError, OSError):
            raise DocumentGenerationError(
                f"{fmt.upper()} generation is unavailable on this machine: required renderer dependencies "
                "could not be loaded. Other document formats remain independent.") from None
    return _GENERATORS.get(fmt)


def renderer_unavailable_reason(fmt: str) -> str:
    """Probe only when readiness is requested, never while starting the assistant."""
    try:
        fn = _generator(fmt)
    except DocumentGenerationError as error:
        return str(error)
    return '' if fn is not None else f'unsupported document format: {fmt}'


def generate(fmt: str, spec: dict[str, Any]) -> GeneratedDocument:
    if not isinstance(spec, dict):
        raise DocumentGenerationError("the content specification must be an object")
    fn = _generator(fmt)
    if fn is None:
        raise DocumentGenerationError(
            f"unsupported document format: {fmt} (supported: {', '.join(supported_formats())})")
    return fn(spec)


#: office layout rendering is registered separately when its optional dependencies exist
RENDERERS: dict[str, "Any"] = {}


# Native rendering libraries are deliberately loaded per requested format.
