"""Dynamic workflows: typed plans, a deterministic interpreter and capability gates.

The design contract is in ``docs/realignment/dynamic-workflows.md``. This package owns:

* ``plan``     - the declarative, model-authorable plan schema (pydantic, strict);
* ``expr``     - the bounded reference/condition evaluator (no ``eval``, no code);
* ``compile``  - validation and lowering to a canonical executable plan with stable ids;
* ``qualify``  - role-specific model capability gates (documented/probed/observed/...);
* ``engine``   - the deterministic interpreter over durable node records;
* ``runner``   - the owned orchestration attempt (claim, dispatch steps, settle, continue).

Nothing here executes generated code. Deterministic nodes run in the orchestration
process through the canonical tool seam; model work runs as ordinary step runs.
"""

from __future__ import annotations

__all__ = ["plan", "expr", "compile", "qualify", "engine", "runner"]
