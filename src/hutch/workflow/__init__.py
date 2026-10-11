"""Dynamic workflows: typed plans, a deterministic interpreter and capability gates.

The design contract is in ``docs/realignment/dynamic-workflows.md``. The package owns:

* ``plan``        - the declarative, model-authorable plan schema (pydantic, strict);
* ``expr``        - the bounded reference/condition evaluator (no ``eval``, no code);
* ``compile``     - validation, lowering and the shared plan-structure view;
* ``ops``         - the reviewed deterministic operation set (pure, strict);
* ``qualify``     - role-specific model capability gates (documented/probed/observed/...);
* ``routing``     - Off/Suggest/Auto policy, auto scope and blocked-role explanations;
* ``persistence`` - durable definitions, revisions, instances, node records and questions;
* ``engine``      - the deterministic interpreter over durable node records;
* ``runtime``     - the owned orchestration attempt (claim, dispatch steps, settle, continue);
* ``submit``      - input validation, authority checks and admission.

Nothing here executes generated code. Deterministic nodes run in the orchestration process
through the canonical tool seam; model work runs as ordinary step runs.
"""
