"""Canonical tool-calling contracts, compilation, and validation.

This package owns the boundary between Hutch's authoritative tool registry and
whatever wire protocol a model backend speaks. See ``docs/realignment/tool-calling.md``
for the plan, evidence ledger, and supported-mode matrix.
"""

from .strictjson import JSONProblem, loads_strict

__all__ = ["JSONProblem", "loads_strict"]
