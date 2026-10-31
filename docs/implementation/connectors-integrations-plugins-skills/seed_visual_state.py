"""Seed a disposable dashboard state for visual validation of /connectors.

Uses the real store and the real service layer (no invented UI state), with a connector whose
server is the repository's own fixture. Nothing here is committed: it writes to a temp state dir.
"""

import json
import pathlib
import shutil
import sys
import tempfile

state = pathlib.Path(sys.argv[1])
state.mkdir(parents=True, exist_ok=True)
package = pathlib.Path.home() / ".hutch-tmp" / "visual-connector"
shutil.rmtree(package, ignore_errors=True)
package.mkdir(parents=True)
shutil.copyfile("tests/fixtures/mcp_stdio_server.py", package / "server.py")

import os

os.environ["HUTCH_STATE_DIR"] = str(state)

from hutch.config import get_config
from hutch.models import Bot
from hutch.store import Store
from hutch.integrations.mcp import service

config = get_config()
config.ensure()
store = Store(config)

reader = store.create_bot(Bot(name="reader", display_name="Reader", model="mock/demo", tools=[]))
writer = store.create_bot(Bot(name="scribe", display_name="Scribe", model="mock/demo", tools=[]))

first = service.configure(store, integration_id="acme", title="Acme workspace",
                          raw_definition={"transport": "mcp_stdio", "command": "/usr/bin/python3",
                                          "args": [str(package / "server.py")],
                                          "read_only_paths": [str(package)]})
# Leave one connector merely installed, so the page shows both states.
service.configure(store, integration_id="beta", title="Beta (not tested)",
                  raw_definition={"transport": "mcp_http", "url": "https://mcp.example.com/mcp",
                                  "auth": {"type": "none"}})
service.discover(store, integration_id="acme")
service.grant(store, integration_id="acme", bot_ref=reader.id, tool_names=["read_workspace"],
              operation_classes={"read_workspace": "read"}, expected_revision=first["revision"])
service.grant(store, integration_id="acme", bot_ref=writer.id,
              tool_names=["write_workspace", "wait_for_cancel"],
              operation_classes={"write_workspace": "write", "wait_for_cancel": "unknown"},
              expected_revision=first["revision"])
print(json.dumps({"bots": [reader.id, writer.id], "state": str(state)}))
