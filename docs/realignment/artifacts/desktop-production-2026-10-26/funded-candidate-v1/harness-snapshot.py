"""Session-owned synthetic qualification; no credential argument or paid fallback."""
from pathlib import Path
from decimal import Decimal
import argparse
import hashlib
import json
import os
import stat
import threading
import time

import httpx
from hutch.approvals import ApprovalGate
from hutch.config import hutchConfig
from hutch.connections import ConnectionBook
from hutch.models import ApprovalMode, Bot, Limits, Run, RunStatus
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.runtime.builtin import BuiltinRuntime
from hutch.runtime import RunAborted
from hutch.safety import PolicyEngine
from hutch.store import Store
from hutch.tools import build_tools
from hutch.tools.base import ToolContext

parser = argparse.ArgumentParser()
parser.add_argument('--model', choices=['deepseek/deepseek-v4.1-flash'], required=True)
parser.add_argument('--case', choices=['final-marketing-01', 'final-marketing-02', 'final-marketing-03', 'final-performance-01', 'final-performance-02', 'final-performance-03', 'final-sales-01', 'final-sales-02', 'final-sales-03'], required=True)
parser.add_argument('--execute', action='store_true')
args = parser.parse_args()
if not args.execute:
    raise SystemExit('Explicit --execute required; no inference sent')
assert not os.environ.get('HUTCH_TESTING'), 'Refuse a fixture-runtime environment'
root = Path(os.environ['HUTCH_EVALUATION_STATE'])
assert not root.is_symlink() and stat.S_IMODE(root.stat().st_mode) == 0o700
book = ConnectionBook(root)
assert list(book.configured()) == ['evaluation-router']
conn = book.get('evaluation-router')
assert conn.template == 'openrouter' and conn.account_id == 'evaluation' and conn.prefer_stored_key
assert conn.base_url.rstrip('/') == 'https://openrouter.ai/api/v1'
policy = conn.openrouter_policy
expected_provider = {'deepseek/deepseek-v3.2': 'deepinfra/fp4', 'deepseek/deepseek-v4.1-flash': 'deepinfra/fp8'}[args.model]
assert policy == {'allow_fallbacks': False, 'order': [expected_provider], 'require_parameters': True,
                  'data_collection': 'deny', 'zdr': True,
                  'max_price': {'prompt': .35, 'completion': .8, 'request': 0}}
assert not book.key_file(conn.name).is_symlink()
assert stat.S_IMODE(book.key_file(conn.name).stat().st_mode) == 0o600
secret = book.key(conn.name)
assert secret
credits = httpx.Client(timeout=15, trust_env=False, follow_redirects=False)


def safe(value):
    return str(value).replace(secret, '<redacted>')


def available_credit():
    response = credits.get('https://openrouter.ai/api/v1/credits', headers={'Authorization': 'Bearer ' + secret})
    if response.status_code != 200:
        raise RuntimeError('Provider credit could not be verified; no request permitted')
    data = response.json()['data']
    amount = Decimal(str(data['total_credits'])) - Decimal(str(data['total_usage']))
    if not amount.is_finite() or amount < 0:
        raise RuntimeError('Provider credit is not a known non-negative amount')
    return amount


config = hutchConfig(state_dir=root)
store = Store(config)
budget = store.get_budget_policy('account', 'evaluation')
phase = json.loads(store.kv_get('evaluation:final:v1'))
assert phase['phase'] == 'final' and phase['allowance_usd'] == 5
assert budget.reset == 'lifetime' and budget.revision == phase['policy_revision'] == 3
assert Decimal(str(budget.ceiling_usd)) == Decimal(str(phase['cumulative_ceiling_usd'])) == Decimal('5.002729993')
assert not store.unresolved_usage_reservations(), 'Reconcile previous uncertain charges before another final repetition'
source_commit = __import__('subprocess').check_output(['git','rev-parse','HEAD'],text=True).strip()
assert not __import__('subprocess').check_output(['git','diff','--name-only','--','src/hutch'],text=True).strip(), 'Runtime source must be committed'
fixture_cases = json.loads(Path('.validation/desktop-production/business-fixtures-v1.json').read_text())
case_kind = args.case.split('-')[1]
fixture = fixture_cases[case_kind]
phase_spent, phase_held = store.scope_spend(scope_kind='account',scope_id='evaluation')
assert available_credit() > 0, 'No credit remains; no request permitted'
# Dispatch additionally requires real remaining credit to cover every current hold; a phase allowance is not a demand to spend it.
workspace = root / 'workspaces' / args.case
workspace.mkdir(parents=True, mode=0o700)
(workspace / 'input.txt').write_text(fixture['input'])
original_input_hash = hashlib.sha256((workspace / 'input.txt').read_bytes()).hexdigest()
bot = store.create_bot(Bot(name=args.case, model='evaluation-router/' + args.model,
    instructions='Complete the requested synthetic fixture task accurately. Do not access networks or run shell commands. All output is a draft. Use canonical Hutch tools for saved files.',
    tools=['read_file', 'write_file'], tool_protocol='native', approval_mode=ApprovalMode.auto,
    memory_enabled=False, selfcheck=False,
    limits=Limits(max_steps=12, max_turn_tokens=4096, timeout_seconds=180, daily_token_cap=100000,
                  max_cost_usd=2)))
run = store.create_run(Run(bot_id=bot.id,
    prompt=f"Read input.txt in your working folder. {fixture['request']} Use Hutch read_file and write_file tools. Return only a short summary when finished."))
claimed = store.claim_run(run.id, 'qualification-owner', 300)
assert claimed
run = store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
checks = []
stop = threading.Event()


def emit(event):
    encoded = json.dumps(event.data).replace(secret, '<redacted>')
    store.append_event(event.model_copy(update={'data': json.loads(encoded)}))


def dispatch_guard(request):
    if request.method != 'POST' or not request.url.path.endswith('/chat/completions'):
        return
    assert request.url.scheme == 'https' and request.url.host == 'openrouter.ai'
    payload = json.loads(request.content)
    assert payload['model'] == args.model and payload.get('provider') == policy
    assert not {'plugins', 'models', 'route'} & set(payload)
    assert 0 < payload.get('max_completion_tokens', payload.get('max_tokens', 0)) <= 4096
    assert {tool['function']['name'] for tool in payload.get('tools', [])} <= {'read_file', 'write_file'}
    current_policy = store.get_budget_policy('account','evaluation')
    assert current_policy.revision == budget.revision and current_policy.ceiling_usd == budget.ceiling_usd
    holds = store.unresolved_usage_reservations(limit=500)
    assert any(row['run_id'] == run.id and row['status'] == 'reserved' for row in holds)
    measured, held = store.scope_spend(scope_kind='account', scope_id='evaluation')
    assert measured + held <= budget.ceiling_usd + 1e-9
    assert len(checks) < 12 and not stop.is_set()
    remaining = available_credit()
    if remaining < Decimal(str(held)) or stop.is_set():
        raise RuntimeError('Remaining credit or cancellation prevents dispatch')
    checks.append({'sequence': len(checks) + 1, 'current_reservation_verified': True,
                   'account_spent_usd': measured, 'account_held_usd': held, 'credit_verified': True})


class QualifiedRuntime(BuiltinRuntime):
    def _provider_for(self, *values, **options):
        provider = super()._provider_for(*values, **options)
        assert isinstance(provider, OpenAICompatProvider) and provider.reports_billed_cost
        assert provider.base_url == 'https://openrouter.ai/api/v1'
        hooks = provider._http().event_hooks['request']
        if dispatch_guard not in hooks:
            hooks.append(dispatch_guard)
        return provider


engine_policy = PolicyEngine(bot.risk_tier, bot.command_rules)
gate = ApprovalGate(store, bot, run, engine_policy, emit, poll_seconds=.05)
ctx = ToolContext(bot=bot, run=run, store=store, policy=engine_policy, gate=gate, config=config,
                  workspace=workspace, emit=emit)
tools = build_tools(bot.tools, ctx)


def cancel():
    stop.set()
    gate.cancel_requested = True


deadline = threading.Timer(180, cancel)
record = {'contract_version': 1, 'case': args.case, 'route': bot.model,
          'scope': 'synthetic guide-derived local final repetition; no UI, external-service or whole-workflow acceptance',
          'permission': 'only preauthorized local fixture reads/writes; isolated Bot auto mode',
          'functional_checks_passed': False, 'artifact_quality': 'independent review required; functional checks alone are not 85/100 acceptance',
          'phase': phase, 'runtime_source_commit': source_commit,
          'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'routing_policy': policy, 'qualification_ceiling_usd': budget.ceiling_usd,
          'fixture_sha256': hashlib.sha256(json.dumps(fixture,sort_keys=True).encode()).hexdigest(),
          'input_sha256': original_input_hash}
started = time.monotonic()
deadline.start()
try:
    answer = QualifiedRuntime().execute(run, ctx, tools, stop.is_set)
    current = store.get_run(run.id)
    if current and current.status == RunStatus.running:
        store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
    import csv, math
    assert hashlib.sha256((workspace / 'input.txt').read_bytes()).hexdigest() == original_input_hash
    if case_kind == 'marketing':
        text = (workspace / 'positioning.md').read_text()
        assert all(value in text for value in ['https://example.com/fixture/birch','https://example.com/fixture/elm','Cedar'])
        assert 'synthetic' in text.lower() and 'draft' in text.lower()
    elif case_kind == 'performance':
        with (workspace / 'metrics.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows)==2 and set(rows[0])=={'campaign','ctr','cvr','cpa','roas','alert'}
        indexed={row['campaign']:row for row in rows}
        search,social=indexed['Search'],indexed['Social']
        for field,value in [('ctr',.1),('cvr',.02),('cpa',15),('roas',3.3333)]:
            assert math.isclose(float(search[field]),value,rel_tol=0,abs_tol=.0001)
        assert search['alert']=='over_budget'
        assert float(social['ctr'])==.02 and float(social['cvr'])==0 and social['cpa']==''
        assert social['alert']=='zero_conversions'
        assert 'approv' in (workspace / 'recommendations.md').read_text().lower()
    else:
        with (workspace / 'outreach.csv').open(newline='') as stream:
            rows=list(csv.DictReader(stream))
        assert len(rows)==1 and rows[0]['id']=='d' and set(rows[0])=={'id','company','contact','draft','status'}
        assert rows[0]['status']=='draft_needs_approval' and rows[0]['draft'].strip()
        summary=(workspace / 'founder-summary.md').read_text().lower()
        assert 'sent' in summary and ('not' in summary or 'nothing' in summary)
    actions = [action for action in store.list_actions(run.id) if action['tool'] == 'write_file' and action['status'] == 'done']
    assert len(actions) >= (1 if case_kind == 'marketing' else 2)
    events = store.list_events(run.id)
    assert any(event.type.value == 'tool_call' and event.data.get('tool') == 'read_file' for event in events)
    record.update(functional_checks_passed=True, done_write_receipts=len(actions), answer=safe(answer))
except Exception as error:
    record.update(error_type=type(error).__name__, error=safe(error))
    current = store.get_run(run.id)
    if current and current.status == RunStatus.running:
        store.transition_run(run.id, RunStatus.failed, fence=run.fence, error=safe(error), exit_reason='evaluation_error')
finally:
    deadline.cancel()
    deadline.join(timeout=1)
    ctx.closed = True
    ctx.procs.finish()
    for finish in ctx.on_finish:
        finish()
    store.flush_events()
    current = store.get_run(run.id)
    rows = store._db.execute('SELECT prompt_tokens,completion_tokens,cost_usd,cost_source,reported_cost_usd FROM usage WHERE run_id=?', (run.id,)).fetchall()
    measured, held = store.scope_spend(scope_kind='account', scope_id='evaluation')
    record.update(runtime_elapsed_seconds=round(time.monotonic() - started, 3),
                  run_status=current.status.value, settled_tokens=current.tokens,
                  run_cost_usd=current.cost_usd, account_spent_usd=measured, account_held_usd=held,
                  requests=checks, usage=[dict(row) for row in rows],
                  held_requests=[row for row in store.unresolved_usage_reservations() if row['run_id'] == run.id],
                  event_chain_ok=store.verify_chain(run.id)['ok'])
    out = Path('.validation/desktop-production') / args.case
    out.mkdir(exist_ok=False)
    (out / 'result.json').write_text(safe(json.dumps(record, indent=2)) + '\n')
    for artifact in workspace.iterdir():
        if artifact.is_file() and artifact.suffix in ('.txt','.md','.csv'):
            (out / ('artifact-' + artifact.name)).write_bytes(artifact.read_bytes())
    credits.close()
    store.close()
    print(safe(json.dumps(record, indent=2)))
