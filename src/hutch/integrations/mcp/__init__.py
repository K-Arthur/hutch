"""Governed MCP client plane (ADR-0017 S2/S3).

MCP is transport between Hutch and an integration. It never replaces model APIs, tool-call
parsing or Hutch's provider conversion, and an MCP tool is an ordinary ``Tool`` in the one
registry, subject to the one approval and receipt path.

Modules:

* ``config``      reviewed definitions, secret hygiene, fingerprints
* ``network``     pinned egress and endpoint screening
* ``transport``   contained stdio launch and client construction
* ``discovery``   bounded normalization of an untrusted tool catalog
* ``persistence`` reviewed servers, catalogs and per-assistant grants
* ``tool``        the adapter that makes an MCP tool an ordinary Hutch tool
* ``service``     the operations the API and the UI call
* ``schema``      the additive migration
"""

from __future__ import annotations

__all__: list[str] = []
