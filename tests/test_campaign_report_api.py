"""Preview is side effect free; saving uses canonical idempotent workflows."""
import json

import pytest

from tests.test_campaign_report import SOURCE
from tests.test_workflow_api import client, make_bot  # noqa: F401


def test_preview_does_not_admit_run_or_save_definition(client):
    response = client.post('/api/v1/workflows/starters/campaign-report/preview',
                           json={"source_csv": SOURCE})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview['report']['rows'][1]['cpa'] is None
    assert preview['report']['reporting_days'] is None
    assert preview['plan']['budget']['max_model_calls'] == 0
    assert preview['plan']['envelope']['tools'] == []
    assert client.get('/api/v1/workflows/runs').json()['items'] == []
    assert client.get('/api/v1/workflows').json()['items'] == []


@pytest.mark.parametrize('change', [{'reporting_days': True}, {'reporting_days': -1},
                                  {'reporting_days': '1'}, {'source_csv': 'invalid'},
                                  {'source_csv': SOURCE.replace('Social', '=FORMULA()')},
                                  {'source_csv': SOURCE.replace('Social', '\ud800')},
                                  {'source_csv': 'é'*40000}])
def test_invalid_preview_cannot_become_a_saved_or_started_workflow(client, change):
    response = client.post('/api/v1/workflows/starters/campaign-report/preview',
                           content=json.dumps({"source_csv": SOURCE, **change}),
                           headers={'Content-Type':'application/json'})
    assert response.status_code == 422
    assert client.get('/api/v1/workflows/runs').json()['items'] == []


def test_reviewed_plan_uses_existing_admission_and_duplicate_suppression(client):
    bot = make_bot(client, tools=[])
    inputs = {'source_csv': SOURCE, 'reporting_days': 1}
    preview = client.post('/api/v1/workflows/starters/campaign-report/preview', json=inputs).json()
    body = {'bot': bot['name'], 'plan': preview['plan'], 'inputs': inputs,
            'save_definition': True}
    headers = {'Idempotency-Key': 'campaign-report-reviewed-once'}
    first = client.post('/api/v1/workflows/plans', json=body, headers=headers)
    assert first.status_code == 201, first.text
    second = client.post('/api/v1/workflows/plans', json=body, headers=headers)
    assert second.status_code == 201, second.text
    assert first.json()['workflow_run_id'] == second.json()['workflow_run_id']
    assert len(client.get('/api/v1/workflows/runs').json()['items']) == 1
    definitions=client.get('/api/v1/workflows').json()['items']
    assert len(definitions)==1 and definitions[0]['active'] is False
