import copy

import pytest

from tests.support.live_models import qualify_free_model


def _row():
    return {'providerID': 'opencode', 'modelID': 'candidate-free', 'status': 'active',
            'limit': {'context': 200000, 'output': 32000}, 'capabilities': {'tools': True},
            'cost': [{'input': 0, 'output': 0, 'cache': {'read': 0, 'write': 0}}]}


def test_exact_free_route_requires_explicit_zero_prices_for_every_tier():
    row = _row()
    row['cost'].append({'input': '0', 'output': '0', 'cache': {'read': 0, 'write': 0},
                        'tier': {'type': 'context', 'size': 100000}})
    assert qualify_free_model([row], 'opencode', 'candidate-free')['advertised_cost_usd'] == 0
    row['cost'][1]['output'] = '.001'
    with pytest.raises(ValueError, match='Every published rate'):
        qualify_free_model([row], 'opencode', 'candidate-free')


@pytest.mark.parametrize('change', [
    {'cost': None}, {'cost': []}, {'cost': [{'input': 0, 'output': 0}]},
    {'cost': [{'input': 0, 'output': 0, 'cache': {'read': 0, 'write': 0}, 'request': .01}]},
    {'cost': [{'input': False, 'output': 0, 'cache': {'read': 0, 'write': 0}}]},
    {'cost': [{'input': 'NaN', 'output': 0, 'cache': {'read': 0, 'write': 0}}]},
    {'status': 'retired'}, {'capabilities': {'tools': False}},
    {'capabilities': 'tools'}, {'limit': []},
    {'limit': {'context': 200000, 'output': 0}},
])
def test_unknown_paid_or_unusable_free_candidates_are_refused(change):
    row = {**_row(), **copy.deepcopy(change)}
    with pytest.raises(ValueError):
        qualify_free_model([row], 'opencode', 'candidate-free')


def test_an_alias_or_duplicate_cannot_qualify_the_requested_route():
    with pytest.raises(ValueError):
        qualify_free_model([_row()], 'opencode-go', 'candidate-free')
    with pytest.raises(ValueError):
        qualify_free_model([_row(), _row()], 'opencode', 'candidate-free')
