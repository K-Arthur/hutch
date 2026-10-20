"""Test-only runtime injection for supervised worker subprocesses."""

from __future__ import annotations

import os

if os.environ.get("HUTCH_TESTING") == "1":
    import hutch.modelchoices as modelchoices
    import hutch.runtime as runtime
    from tests.support.runtime import test_model_choices_for, test_runtime_for, test_validate_override_for

    _production_factory = runtime.get_runtime
    _production_choices = modelchoices.model_choices
    _production_validate = modelchoices.validate_override

    def _test_runtime_factory(bot):
        return test_runtime_for(bot, _production_factory)

    runtime.get_runtime = _test_runtime_factory
    modelchoices.model_choices = lambda *args, **kwargs: test_model_choices_for(
        args[2], args, kwargs, _production_choices)
    modelchoices.validate_override = lambda config, store, bot, spec, *args, **kwargs: test_validate_override_for(
        bot, spec, (config, store, bot, spec, *args), kwargs, _production_validate)
