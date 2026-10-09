"""Test-only runtime injection for supervised worker subprocesses."""

from __future__ import annotations

import os

if os.environ.get("HUTCH_TESTING") == "1":
    import hutch.runtime as runtime
    from tests.support.runtime import test_runtime_for

    _production_factory = runtime.get_runtime

    def _test_runtime_factory(bot):
        return test_runtime_for(bot, _production_factory)

    runtime.get_runtime = _test_runtime_factory
