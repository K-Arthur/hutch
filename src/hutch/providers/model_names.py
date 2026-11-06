"""Model-name grammar shared by install, remove and duplicate checks.

The grammar is Ollama's own (``types/model/name.go``): a host, namespace, model and tag,
with defaults ``registry.ollama.ai``, ``library`` and ``latest``. It is not a lowercase
slug: a host may carry a port, model and tag are case-preserving, and equality is
case-insensitive. Hugging Face pulls use the same shape with ``hf.co`` as the host and a
quantization (or a GGUF filename) as the tag, so the parser accepts those without a
special case.

The parser validates syntax only. Whether a name is cloud-routed is a separate decision
made from the runtime's signal and, only as a fallback, from the tag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_HOST = "registry.ollama.ai"
DEFAULT_NAMESPACE = "library"
DEFAULT_TAG = "latest"
MAX_NAME_CHARS = 600

_HOST = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,349}")
_NAMESPACE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,79}")
_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,79}")
_DIGEST = re.compile(r"sha256:[0-9a-fA-F]{64}")


@dataclass(frozen=True)
class ModelName:
    """A parsed name. Defaults are filled in, so every name is fully qualified."""

    host: str
    namespace: str
    model: str
    tag: str
    digest: str = ""

    def canonical(self) -> str:
        """The shortest form that means the same thing: defaults are omitted."""
        if self.host.casefold() != DEFAULT_HOST:
            base = f"{self.host}/{self.namespace}/{self.model}"
        elif self.namespace.casefold() != DEFAULT_NAMESPACE:
            base = f"{self.namespace}/{self.model}"
        else:
            base = self.model
        out = f"{base}:{self.tag}"
        return f"{out}@{self.digest}" if self.digest else out

    def key(self) -> tuple[str, str, str, str]:
        """Case-insensitive identity; the digest is deliberately not part of it."""
        return (self.host.casefold(), self.namespace.casefold(),
                self.model.casefold(), self.tag.casefold())


def _refuse(raw: str, part: str, example: str) -> ValueError:
    return ValueError(f"'{raw}' is not a valid model name: the {part} is invalid. "
                      f"Use host/namespace/model:tag, for example {example}")


def _part(raw: str, value: str, pattern: re.Pattern[str], part: str, example: str) -> str:
    if not pattern.fullmatch(value):
        raise _refuse(raw, part, example)
    return value


def parse_model_name(raw: str) -> ModelName:
    """Parse a real model name or raise ``ValueError`` with the offending part.

    Accepted forms: ``model``, ``model:tag``, ``namespace/model:tag``,
    ``host/namespace/model:tag`` and an optional ``@sha256:<64 hex>`` suffix. The tag may
    be a quantization such as ``Q4_K_M`` or a full ``.gguf`` filename, as Hugging Face
    publishes them.
    """
    candidate = (raw or "").strip()
    if not candidate:
        raise ValueError("a model name is required, for example qwen3:4b")
    if len(candidate) > MAX_NAME_CHARS:
        raise ValueError("model name is too long")

    digest = ""
    if "@" in candidate.rsplit("/", 1)[-1]:
        candidate, _, digest_text = candidate.rpartition("@")
        if not _DIGEST.fullmatch(digest_text):
            raise ValueError("a pinned digest must look like @sha256:<64 hex characters>")
        digest = digest_text.lower()
    if not candidate:
        raise ValueError("a model name is required before the digest")

    head, tag = candidate, DEFAULT_TAG
    colon, slash = candidate.rfind(":"), candidate.rfind("/")
    if colon > slash:
        head, tag = candidate[:colon], candidate[colon + 1:]
        _part(raw, tag, _PART, "tag", "qwen3:4b or hf.co/user/repo:Q4_K_M")

    parts = head.split("/")
    if len(parts) == 1:
        host, namespace, model = DEFAULT_HOST, DEFAULT_NAMESPACE, parts[0]
    elif len(parts) == 2:
        host, namespace, model = DEFAULT_HOST, parts[0], parts[1]
    elif len(parts) == 3:
        host, namespace, model = parts
    else:
        raise ValueError(f"'{raw}' is not a valid model name: use at most host/namespace/model:tag")

    _part(raw, host, _HOST, "host", "registry.ollama.ai/library/qwen3:4b")
    _part(raw, namespace, _NAMESPACE, "namespace", "library/qwen3:4b")
    _part(raw, model, _PART, "model", "qwen3:4b")
    return ModelName(host=host, namespace=namespace, model=model, tag=tag, digest=digest)


def same_model(a: str, b: str) -> bool:
    """True when two spellings name the same model (Ollama compares case-insensitively).

    A malformed name never raises here: the caller is usually comparing a runtime's own
    list with a user's input, and an unfamiliar entry must not break duplicate checks.
    """
    try:
        left, right = parse_model_name(a), parse_model_name(b)
    except ValueError:
        return (a or "").strip().casefold() == (b or "").strip().casefold()
    if left.key() != right.key():
        return False
    if left.digest and right.digest and left.digest != right.digest:
        return False
    return True
