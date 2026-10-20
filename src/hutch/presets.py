"""Task presets and the model catalog (LM-7).

Users pick a *task*; Hutch resolves it to a local model that fits this machine, plus an optional hosted model to
escalate to. The resolver prefers a model that is already installed, only suggests an install when nothing
installed fits, and says plainly when nothing local fits at all (then the preset is hosted-only).

Candidates are suggestions. Whether a model is actually *good at tool calling here* is measured on this machine
(`hutch models bench`, LM-11), never assumed from a blog post.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Optional

from .fit import Fit, estimate_fit
from .hardware import GIB, Hardware
from .providers.base import ModelMeta

TIERS = ["tiny", "small", "medium", "large", "xl"]


def _data(name: str) -> dict:
    return json.loads(Path(str(resources.files("hutch") / "data" / name)).read_text())


def _validate_preset(pid: str, row: dict) -> None:
    """Reject structurally invalid user overrides with a field-specific message."""
    def fail(field: str, expected: str) -> None:
        raise ValueError(f"invalid presets.{pid}.{field}: expected {expected}")

    for field in ("title", "description", "hosted"):
        if field in row and not isinstance(row[field], str):
            fail(field, "a string")
    for field in ("want_ctx", "min_ctx"):
        value = row.get(field, 16384 if field == "want_ctx" else 8192)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            fail(field, "a positive integer")
    for field in ("needs",):
        value = row.get(field, ["tools"])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            fail(field, "a list of strings")
    limits = row.get("limits", {})
    if not isinstance(limits, dict):
        fail("limits", "an object")
    local = row.get("local", {})
    if not isinstance(local, dict) or any(
        not isinstance(tier, str) or not isinstance(models, list)
        or any(not isinstance(model, str) for model in models)
        for tier, models in local.items()
    ):
        fail("local", "an object of model-name lists")
    if "keep_resident" in row and not isinstance(row["keep_resident"], bool):
        fail("keep_resident", "a boolean")


@dataclass
class Preset:
    id: str
    title: str
    description: str
    needs: list[str]
    want_ctx: int
    min_ctx: int
    limits: dict
    local: dict[str, list[str]]
    hosted: str
    keep_resident: bool = False


@dataclass
class Resolution:
    preset: Preset
    local_model: Optional[str]            # ollama tag, or None when nothing local fits
    installed: bool
    fit: Optional[Fit]
    hosted: str
    reason: str
    install_hint: str = ""
    considered: list[tuple[str, str]] = field(default_factory=list)   # (model, why not)

    @property
    def local_spec(self) -> Optional[str]:
        return f"ollama/{self.local_model}" if self.local_model else None


def load_presets(user_path: Optional[Path] = None) -> dict[str, Preset]:
    data = _data("presets.json")
    rows = dict(data["presets"])
    hosted_default = data.get("hosted_default", "anthropic/claude-opus-5-5")
    if user_path and user_path.exists():
        try:
            user = json.loads(user_path.read_text())
            if not isinstance(user, dict):
                raise ValueError("invalid presets file: expected a JSON object")
            hosted_default = user.get("hosted_default", hosted_default)
            if not isinstance(hosted_default, str):
                raise ValueError("invalid presets.hosted_default: expected a string")
            overrides = user.get("presets", {})
            if not isinstance(overrides, dict):
                raise ValueError("invalid presets.presets: expected an object")
            for k, v in overrides.items():
                if not isinstance(k, str) or not isinstance(v, dict):
                    raise ValueError("invalid presets.presets: expected preset names mapped to objects")
                _validate_preset(k, v)
                rows[k] = {**rows.get(k, {}), **v}
        except (OSError, json.JSONDecodeError):
            pass
    out = {}
    for pid, p in rows.items():
        out[pid] = Preset(id=pid, title=p.get("title", pid), description=p.get("description", ""),
                          needs=p.get("needs", ["tools"]), want_ctx=int(p.get("want_ctx", 16384)),
                          min_ctx=int(p.get("min_ctx", 8192)), limits=p.get("limits", {}), local=p.get("local", {}),
                          hosted=p.get("hosted", hosted_default), keep_resident=bool(p.get("keep_resident")))
    return out


def catalog_meta(tag: str) -> Optional[ModelMeta]:
    row = _data("catalog.json")["models"].get(tag)
    if row is None:
        return _meta_from_tag(tag)
    return ModelMeta(name=tag, params_b=row.get("params_b"), quant=row.get("quant", ""),
                     size_bytes=int(row["size_gb"] * GIB) if row.get("size_gb") else None,
                     max_context=row.get("max_context"), n_layers=row.get("layers"), n_kv_heads=row.get("kv_heads"),
                     head_dim=row.get("head_dim"), capabilities=list(row.get("caps", [])),
                     license=row.get("license", ""))


def _meta_from_tag(tag: str) -> Optional[ModelMeta]:
    """A model we have no catalog row for: guess parameters from the tag ('llama3.1:8b' -> 8B)."""
    m = re.search(r":?(\d+(?:\.\d+)?)b\b", tag.lower())
    return ModelMeta(name=tag, params_b=float(m.group(1)), quant="Q4_K_M") if m else None


def resolve_preset(preset: Preset, hw: Hardware, installed: dict[str, ModelMeta]) -> Resolution:
    """Best local model for this task on this machine: installed + fitting first, then fitting, else none."""
    start = TIERS.index(hw.tier)
    candidates: list[str] = []
    for tier in reversed(TIERS[: start + 1]):        # this tier first, then smaller ones
        candidates += [c for c in preset.local.get(tier, []) if c not in candidates]
    considered: list[tuple[str, str]] = []
    viable: list[tuple[str, Fit, bool]] = []          # (tag, fit, installed) in preference order
    for tag in candidates:
        meta = installed.get(tag) or catalog_meta(tag)
        if meta is None:
            considered.append((tag, "no size information"))
            continue
        missing = [n for n in preset.needs if meta.capabilities and n not in meta.capabilities]
        if missing:
            considered.append((tag, f"lacks {', '.join(missing)}"))
            continue
        fit = estimate_fit(meta, hw, preset.want_ctx, min_ctx=preset.min_ctx)
        if fit.status == "wont_fit":
            considered.append((tag, fit.reason))
            continue
        viable.append((tag, fit, tag in installed))
    # A model that FITS beats one squeezed into a smaller window ("tight"); installed beats a download.
    for want_status in ("fits", "tight"):
        pool = [v for v in viable if v[1].status == want_status]
        pick = next((v for v in pool if v[2]), None) or (pool[0] if pool else None)
        if pick:
            tag, fit, have = pick
            if have:
                return Resolution(preset, tag, True, fit, preset.hosted,
                                  f"{tag} is installed and '{fit.label}' ({fit.reason})", considered=considered)
            return Resolution(preset, tag, False, fit, preset.hosted,
                              f"{tag} would be '{fit.label}' here ({fit.reason}) but is not installed",
                              install_hint=f"ollama pull {tag}", considered=considered)
    return Resolution(preset, None, False, None, preset.hosted,
                      f"no local model fits this machine for '{preset.title}' (budget {hw.budget_gb:.1f} GiB); "
                      f"use the hosted model {preset.hosted}", considered=considered)
