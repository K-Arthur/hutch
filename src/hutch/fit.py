"""Will this model fit, and with how much context? (LM-5)

The honest answer needs the *context*, not just the weights: the KV cache grows linearly with the window, and an
agent that asks for 32k tokens on an 8 GB machine will either fail to load or be pushed onto the CPU. So each
model is marked **fits / tight / won't fit** and shows the context it will *actually* get.

    weights  = size on disk (installed) or params x bits-per-weight (suggestions)
    kv(ctx)  = 2 x layers x kv_heads x head_dim x ctx x 2 bytes          (fp16 KV; the standard formula)
    need     = weights + kv(ctx) + runtime overhead

Installed models use the runtime's own metadata (layers, KV heads, head size). Suggested-but-not-installed models
use catalog estimates and are labelled as estimates. This is arithmetic, not a benchmark: it does not predict speed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .hardware import GIB, Hardware
from .providers.base import ModelMeta

#: effective bits per weight for common GGUF quantisations (includes block scales)
QUANT_BITS = {
    "Q2_K": 3.0, "Q3_K_M": 3.9, "Q4_0": 4.5, "Q4_1": 5.0, "Q4_K_S": 4.6, "Q4_K_M": 4.85, "Q5_0": 5.5,
    "Q5_K_S": 5.5, "Q5_K_M": 5.7, "Q6_K": 6.6, "Q8_0": 8.5, "F16": 16.0, "BF16": 16.0, "F32": 32.0,
    "MXFP4": 4.3, "NVFP4": 4.5, "IQ4_NL": 4.5, "IQ4_XS": 4.3,
}
DEFAULT_BITS = 4.85
OVERHEAD_GIB = 0.6
KV_BYTES_PER_ELEM = 2
MIN_USEFUL_CTX = 4096
TIGHT_BELOW = 0.85   # needing more than this share of the budget is "tight"


@dataclass
class Fit:
    status: str                 # fits | tight | wont_fit
    effective_ctx: int          # tokens the model will actually get
    wanted_ctx: int
    weights_gib: float
    kv_gib_at_wanted: float
    need_gib: float             # at the wanted context
    budget_gib: float
    max_ctx_fit: int            # largest window that fits the budget
    estimated: bool             # catalog estimate rather than the runtime's own numbers
    reason: str

    @property
    def label(self) -> str:
        return {"fits": "fits", "tight": "tight", "wont_fit": "won't fit"}[self.status]


def weights_gib(meta: ModelMeta) -> tuple[float, bool]:
    if meta.size_bytes:
        return meta.size_bytes / GIB, False
    if meta.params_b:
        bits = QUANT_BITS.get(meta.quant.upper(), DEFAULT_BITS) if meta.quant else DEFAULT_BITS
        return meta.params_b * 1e9 * bits / 8 / GIB, True
    return 0.0, True


def kv_bytes_per_token(meta: ModelMeta) -> tuple[float, bool]:
    if meta.n_layers and meta.n_kv_heads and meta.head_dim:
        return 2.0 * meta.n_layers * meta.n_kv_heads * meta.head_dim * KV_BYTES_PER_ELEM, False
    if meta.params_b:                       # no architecture numbers: ~16 KiB per billion parameters
        return meta.params_b * 16 * 1024, True
    return 128 * 1024, True


def estimate_fit(meta: ModelMeta, hw: Hardware, wanted_ctx: int, *, min_ctx: int = MIN_USEFUL_CTX,
                 budget_gib: Optional[float] = None) -> Fit:
    budget = budget_gib if budget_gib is not None else hw.budget_gb
    w, w_est = weights_gib(meta)
    kv_tok, kv_est = kv_bytes_per_token(meta)
    estimated = w_est or kv_est
    room = budget - w - OVERHEAD_GIB
    cap = meta.max_context or 10 ** 9
    max_fit = int(max(0.0, room) * GIB / kv_tok) if kv_tok else 0
    effective = max(0, min(wanted_ctx, max_fit, cap))
    need = w + OVERHEAD_GIB + kv_tok * min(wanted_ctx, cap) / GIB
    kv_wanted = kv_tok * min(wanted_ctx, cap) / GIB

    if w + OVERHEAD_GIB > budget or effective < min(min_ctx, wanted_ctx):
        why = (f"the weights alone are {w:.1f} GiB against {budget:.1f} GiB usable" if w + OVERHEAD_GIB > budget
               else f"only {effective:,} tokens of context fit after the {w:.1f} GiB of weights "
                    f"(needs at least {min_ctx:,})")
        return Fit("wont_fit", effective, wanted_ctx, w, kv_wanted, need, budget, max_fit, estimated, why)
    if effective < wanted_ctx or need > budget * TIGHT_BELOW:
        why = (f"context is limited to {effective:,} of the {wanted_ctx:,} tokens wanted" if effective < wanted_ctx
               else f"needs {need:.1f} of {budget:.1f} GiB usable: little headroom for the OS and other apps")
        return Fit("tight", effective, wanted_ctx, w, kv_wanted, need, budget, max_fit, estimated, why)
    return Fit("fits", effective, wanted_ctx, w, kv_wanted, need, budget, max_fit, estimated,
               f"{need:.1f} of {budget:.1f} GiB usable at {wanted_ctx:,} tokens")
