"""Grounding: canonical evidence, live acquisition, temporal disambiguation, media checks.

The package is intentionally a set of small, dependency-free modules:

* ``clock``     one injected clock (UTC instants, IANA civil time, monotonic durations)
* ``temporal``  timestamp roles, precision, anchored relative phrases, as-of cutoffs
* ``dedup``     deduplication, origin clusters, explainable noise indicators
* ``acquire``   bounded fan-out adapters with distinct outcomes and local date validation
* ``streams``   versioned cursors, SSE/at-least-once reading, honest liveness
* ``media``     bounded media acquisition, frame sampling, C2PA presence, no verdicts
* ``report``    claim/evidence binding, separate assessment axes, citation-safe briefs

Store tables (schema v53) keep investigations, attempts, source revisions, claims,
evidence links, media artifacts/observations, answers and stream cursors; the tools in
``hutch.tools.live`` and the upgraded ``web_fetch`` write through them.
"""

from .clock import Clock, ClockRef, FrozenClock, SystemClock, UnknownZone, SYSTEM_CLOCK  # noqa: F401
from .temporal import EvidenceCutoff, Precision, TimestampRole, TimestampValue  # noqa: F401
