"""Browser synchronization helpers compatible with Hutch's strict script CSP."""

from time import monotonic, sleep


def wait_for_page(page, expression, *, arg=None, timeout=30_000):
    """Poll a read-only page predicate without Playwright's CSP-blocked eval helper."""
    deadline = monotonic() + timeout / 1000
    while monotonic() < deadline:
        if page.evaluate(expression, arg):
            return True
        sleep(0.05)
    raise AssertionError(f"page predicate did not become true within {timeout} ms: {expression}")


def wait_for_page_value(page, expression, *, arg=None, timeout=30_000):
    """Poll a page expression and return its first truthy value from that same DOM read."""
    deadline = monotonic() + timeout / 1000
    while monotonic() < deadline:
        value = page.evaluate(expression, arg)
        if value:
            return value
        sleep(0.05)
    raise AssertionError(f"page expression did not return a value within {timeout} ms: {expression}")
