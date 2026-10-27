"""Fail-closed qualification for synthetic evaluations on advertised free routes."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def qualify_free_model(rows, provider, model):
    if not isinstance(rows, list) or len(rows) > 4096:
        raise ValueError('Native model metadata must be a bounded list')
    matches = [row for row in rows if isinstance(row, dict) and row.get('providerID') == provider
               and (row.get('modelID') or row.get('id')) == model]
    if len(matches) != 1:
        raise ValueError('The exact evaluation route must have one current metadata entry')
    row = matches[0]
    limits, capabilities = row.get('limit') or {}, row.get('capabilities') or {}
    if not isinstance(limits, dict) or not isinstance(capabilities, dict):
        raise ValueError('Native model limits and capabilities must be objects')
    if row.get('status') != 'active' or capabilities.get('tools') is not True:
        raise ValueError('The evaluation route must be active and advertise tool support')
    if any(type(limits.get(key)) is not int or limits[key] <= 0 for key in ('context', 'output')):
        raise ValueError('The evaluation route must publish positive context and output limits')
    costs = row.get('cost')
    if not isinstance(costs, list) or not 1 <= len(costs) <= 64:
        raise ValueError('Missing native cost metadata is not free')
    for cost in costs:
        if not isinstance(cost, dict) or set(cost) - {'input', 'output', 'cache', 'tier'}:
            raise ValueError('Unknown native fee dimensions require separate qualification')
        cache = cost.get('cache')
        if not isinstance(cache, dict) or set(cache) != {'read', 'write'}:
            raise ValueError('Cache prices must be explicit for free qualification')
        for value in (cost.get('input'), cost.get('output'), cache['read'], cache['write']):
            if isinstance(value, str) and len(value) > 128:
                raise ValueError('Native price values must be bounded')
            try:
                rate = Decimal(str(value)) if type(value) in (str, int, float) else Decimal('NaN')
            except InvalidOperation:
                rate = Decimal('NaN')
            if not rate.is_finite() or rate != 0:
                raise ValueError('Every published rate and tier must be a known zero')
    return {'contract_version': 1, 'provider': provider, 'model': model,
            'context': limits['context'], 'output': limits['output'],
            'checked_at': datetime.now(timezone.utc).isoformat(), 'advertised_cost_usd': 0,
            'scope': 'synthetic evaluation only; metadata is not remote entitlement or billing proof'}
