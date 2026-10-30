"""Shared helpers moved out of test_bot_deletion.py to keep it under the file-size cap."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from hutch.models import Bot, iso, utcnow
from hutch.store import Store
from tests.support.bot_deletion_assert import SENTINEL


digest = 'a' * 64

def now_iso() -> str:
    """One canonical timestamp for fixture rows."""
    return iso(utcnow())


def insert_row(db: sqlite3.Connection, table: str, **values) -> int:
    """Insert one explicit fixture row; callers pass every required column."""
    columns = ', '.join(values)
    marks = ', '.join('?' for _ in values)
    cursor = db.execute(f'INSERT INTO {table} ({columns}) VALUES ({marks})', tuple(values.values()))
    return int(cursor.lastrowid or 0)


def make_files(store, seed: dict) -> dict:
    """Create the managed files this Bot owns plus the user-owned paths that must survive."""
    state = Path(store.config.state_dir)
    created = {}

    def write(relative: str, text: str) -> Path:
        """Create one fixture file under the state directory."""
        path = state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    created['run_dir'] = write('bots/' + seed['name'] + '/runs/' + seed['run'] + '/workspace/artifact.txt', SENTINEL)
    created['workspace'] = write('workspaces/' + seed['bot'] + '/notes.txt', SENTINEL)
    created['profile'] = write('browser-profiles/' + seed['bot'] + '/profile.txt', SENTINEL)
    created['conversation'] = write('workspaces/' + seed['conversation'] + '/upload.txt', SENTINEL)
    created['document'] = write('documents/' + seed['document'] + '/v001-abcdef12/file.md', SENTINEL)
    created['synthesis'] = write('synthesis/' + seed['syn_storage_path'], SENTINEL)
    created['code_worktree'] = write('code-worktrees/' + seed['handoff'] + '/user-code.txt', SENTINEL)
    created['backup'] = write('hutch.db.bak-v82', 'backup')
    return created


def seed_bot(store, name: str, tag: str) -> dict:
    """Seed one rich Bot across the store families the erase inventory names."""
    db = store._db
    stamp = now_iso()
    digest = 'a' * 64 if tag == SENTINEL else 'b' * 64
    bot = store.create_bot(Bot(name=name, display_name=name.replace('-', ' ').title()))
    seed = {'bot': bot.id, 'name': name, 'tag': tag}
    conversation, message, run = _seed_core(store, db, bot, seed, stamp, tag, digest, name)
    _seed_store_records(db, bot, seed, stamp, tag, digest, conversation, run)
    _seed_workspace_and_investigations(db, bot, seed, stamp, tag, digest, name,
                                       conversation, message, run)
    _seed_synthesis(db, bot, seed, stamp, tag, digest, conversation, run)
    _seed_workflows(db, bot, seed, stamp, tag, digest, conversation, run)
    _seed_handoffs_and_sessions(store, db, bot, seed, stamp, tag, digest, conversation, message, run)
    question = 'q_' + bot.id
    insert_row(db, 'conversation_questions', id=question, conversation_id=conversation, run_id=run,
               bot_id=bot.id, assistant_message_id=message, question=tag, selection_mode='single',
               options_json=json.dumps([tag]), status='pending', created_at=stamp)
    db.execute('UPDATE messages SET choice_question_id = ? WHERE id = ?', (question, message))
    db.commit()
    fact = store.remember(bot.id, 'favourite-' + tag[-4:], tag, conversation_id=conversation)
    store.review_fact(bot.id, fact.id, content_hash=fact.content_hash, action='approve', actor='fixture')
    seed['fact'] = fact.id
    db.commit()
    seed['files'] = make_files(store, seed)
    return seed


def _seed_core(store, db, bot, seed, stamp, tag, digest, name):
    """Create the Bot's conversation, reply chain, run, receipts, budget and markers."""
    conversation = 'conv_' + bot.id
    seed['conversation'] = conversation
    insert_row(db, 'conversations', id=conversation, bot_id=bot.id, title=tag + ' chat',
               created_at=stamp, updated_at=stamp)
    message = 'msg_' + bot.id
    seed['message'] = message
    Store._insert_conversation_message(db, message_id=message, conversation_id=conversation, seq=1,
                                       run_id='', role='user', content=tag, created_at=stamp)
    assistant = 'amsg_' + bot.id
    seed['assistant_message'] = assistant
    Store._insert_conversation_message(db, message_id=assistant, conversation_id=conversation, seq=2,
                                       run_id='', role='assistant', content=tag + ' reply',
                                       created_at=stamp)
    reply = 'rmsg_' + bot.id
    Store._insert_conversation_message(db, message_id=reply, conversation_id=conversation, seq=3,
                                       run_id='', role='user', content=tag + ' follow-up',
                                       created_at=stamp, reply_to_message_id=assistant)
    run = 'run_' + bot.id
    seed['run'] = run
    insert_row(db, 'runs', id=run, bot_id=bot.id, doc=json.dumps({'prompt': tag, 'workspace': 'managed'}),
               status='succeeded', created_at=stamp, conversation_id=conversation)
    insert_row(db, 'events', run_id=run, ts=stamp, type='message', data=json.dumps({'text': tag}),
               seq=1, hash='h1', event_key='event-1-' + bot.id)
    insert_row(db, 'run_procs', run_id=run, pid=1, pgid=1, started_at=stamp)
    insert_row(db, 'run_compactions', id='compact_' + bot.id, run_id=run, seq=1, created_at=stamp,
               reason='budget', before_tokens=1, after_tokens=1, status='done', summary_text=tag)
    insert_row(db, 'transcript_delivery', run_id=run, bot_name=name, target_seq=1, delivered_seq=1,
               error='', file_size=1, file_mtime_ns=1)
    action = 'act_' + bot.id
    seed['action'] = action
    insert_row(db, 'tool_actions', id=action, run_id=run, tool='shell',
               idem_key='idem-action-' + bot.id,
               effect='process', summary=tag, status='done', started_at=stamp, finished_at=stamp,
               result_digest=digest, intent_json=json.dumps({'arguments': tag}), intent_hash=digest,
               result_json=json.dumps({'stdout': tag}))
    insert_row(db, 'action_reconciliations', action_id=action, run_id=run, intent_hash=digest,
               outcome='confirmed_done', evidence=tag, recorded_by='operator', recorded_at=stamp)
    insert_row(db, 'approvals', id='appr_' + bot.id, run_id=run, bot_id=bot.id, status='pending',
               created_at=stamp, doc=json.dumps({'action': tag, 'arguments': {'command': tag}}),
               action_hash=digest, expires_at=stamp)
    resets = {'bot': 'lifetime', 'run': 'run_lifetime', 'conversation': 'conversation_lifetime'}
    for scope_kind, scope_id in (('bot', bot.id), ('run', run), ('conversation', conversation)):
        insert_row(db, 'budget_policies', scope_kind=scope_kind, scope_id=scope_id, currency='USD',
                   reset=resets[scope_kind], revision=1, updated_at=stamp)
    insert_row(db, 'budget_pause_releases', scope_kind='bot', scope_id=bot.id, route_hash='route',
               cycle_key='cycle', policy_revision=1, quote_usd=0.0, approval_id='appr_' + bot.id,
               created_at=stamp, request_hash=digest)
    insert_row(db, 'budget_pause_releases', scope_kind='run', scope_id=run, route_hash='route',
               cycle_key='cycle', policy_revision=1, quote_usd=0.0, created_at=stamp,
               request_hash=digest)
    insert_row(db, 'kv', key='selfcheck:' + bot.id, value='1')
    insert_row(db, 'kv', key='schedule:' + bot.id + ':last_fire', value=stamp)
    generation = insert_row(db, 'doc_index_generations', status='active', source_hashes='{}',
                            created_at=stamp)
    chunk = insert_row(db, 'doc_index_chunks', generation=1, doc_name='global-doc.md',
                       doc_sha256=digest, page=1, chunk_index=0, extraction='text',
                       content='global user documentation')
    insert_row(db, 'doc_index_fts', rowid=chunk, content='global user documentation',
               doc_name='global-doc.md', doc_sha256=digest)
    return conversation, message, run


def _seed_store_records(db, bot, seed, stamp, tag, digest, conversation, run) -> None:
    """Fixture rows for job, event_sources, usage, documents, uploads and channels."""
    job = 'job_' + bot.id
    seed['job'] = job
    insert_row(db, 'jobs', id=job, bot_id=bot.id, kind='schedule',
               occurrence_key='2026-10-29T00:00:00Z-' + bot.id,
               created_at=stamp, updated_at=stamp, status='succeeded',
               input=json.dumps({'prompt': tag}))
    insert_row(db, 'job_steps', job_id=job, step_key='step-1', attempt=1, status='succeeded',
               output=json.dumps({'output': tag}), updated_at=stamp)
    source = 'src_' + bot.id
    insert_row(db, 'event_sources', id=source, bot_id=bot.id, kind='feed', name=tag,
               config=json.dumps({'url': tag}), next_check_at=stamp, created_at=stamp)
    insert_row(db, 'source_events', source_id=source, source_revision=1,
               event_key='source-event-1', kind='entry', occurrence='occ-1', summary=tag,
               received_at=stamp, run_id=run, job_id=job)
    insert_row(db, 'tasks', id='task_' + bot.id, bot_id=bot.id, kind='chat', prompt=tag, created_at=stamp)
    insert_row(db, 'schedule_identities', schedule_id='schedule:' + bot.id, bot_id=bot.id, created_at=stamp)
    insert_row(db, 'schedule_occurrences_v20', schedule_id='schedule:' + bot.id,
               occurrence='2026-10-29T00:00:00+00:00', bot_id=bot.id, run_id=run, claimed_at=stamp)
    insert_row(db, 'usage', ts=stamp, run_id=run, bot_id=bot.id, provider='mock', model='demo',
               prompt_tokens=1, completion_tokens=1, cached_tokens=0, cost_usd=0.0)
    insert_row(db, 'usage_reservations', id='res_' + bot.id, run_id=run, bot_id=bot.id, provider='mock',
               account_id='acct', model='demo', status='active', created_at=stamp)
    document = 'doc_' + bot.id
    seed['document'] = document
    insert_row(db, 'documents', id=document, bot_id=bot.id, conversation_id=conversation, title=tag,
               format='md', current_version=1, created_at=stamp)
    insert_row(db, 'document_versions', document_id=document, version=1, filename='file.md',
               storage_name='file.md', mime='text/markdown', bytes=1, sha256=digest,
               storage_path=document + '/v001-abcdef12/file.md', source='generated', run_id=run,
               validation_state='passed', preview_mode='download_only', created_at=stamp)
    insert_row(db, 'uploads', id='upl_' + bot.id, conversation_id=conversation, filename=tag,
               mime='text/plain', byte_size=1, sha256=digest, state='ready', created_at=stamp)
    channel = 'chan_' + bot.id
    insert_row(db, 'channel_connections', id=channel, kind='telegram', name=tag, bot_id=bot.id,
               credential_digest=digest, credential_ref='ref', remote_bot_id='remote-' + bot.id,
               allowed_senders='[]', accept_after=stamp, next_poll_at=stamp, created_at=stamp)
    event_id = insert_row(db, 'channel_events', channel_id=channel, revision=1, external_id='ext-1',
                          sender=tag, text=tag, content_hash=digest, received_at=stamp, run_id=run)
    insert_row(db, 'channel_deliveries', event_id=event_id, text=tag, next_attempt_at=stamp)
    insert_row(db, 'idempotency_keys', scope='api:v1:conversations:' + bot.id, key='receipt-key',
               request_hash=digest, response_json=json.dumps({'conversation_id': conversation, 'title': tag}),
               created_at=stamp)


def _seed_workspace_and_investigations(db, bot, seed, stamp, tag, digest, name, conversation,
                                      message, run) -> None:
    """Fixture rows for workspace tasks, checkpoints and investigations."""
    task = 'wtask_' + bot.id
    seed['workspace_task'] = task
    insert_row(db, 'workspace_tasks', id=task, parent_conversation_id=conversation, source_run_id=run,
               source_user_message_id=message, source_assistant_message_id=message,
               target_bot_id=bot.id, target_display_name=name, original_request=tag,
               proposed_brief=tag, task_brief=tag, child_conversation_id=conversation,
               child_run_id=run, created_at=stamp)
    event_row = db.execute('SELECT id FROM events WHERE run_id = ? ORDER BY id DESC LIMIT 1', (run,)).fetchone()
    insert_row(db, 'workspace_task_checkpoints', workspace_task_id=task, child_run_id=run,
               event_id=event_row[0], event_seq=1, event_type='message', run_status='succeeded',
               kind='terminal', recovery_state='none', created_at=stamp)
    investigation = 'inv_' + bot.id
    seed['investigation'] = investigation
    insert_row(db, 'investigations', id=investigation, run_id=run, conversation_id=conversation,
               bot_id=bot.id, question=tag, question_kind='general', status='done',
               reference_instant=stamp, as_of_instant=stamp, created_at=stamp, updated_at=stamp,
               revision=1, budget_json='{}', coverage_json='{}')
    insert_row(db, 'inv_sources', id='invsrc_' + bot.id, investigation_id=investigation, item_key='i1',
               adapter='web', lane='web', platform='web', kind='page', url=tag, canonical_url=tag,
               origin='web', origin_id='o1', title=tag, excerpt=tag, retrieved_at=stamp)
    insert_row(db, 'inv_claims', id='invclaim_' + bot.id, investigation_id=investigation, text=tag,
               created_at=stamp)
    insert_row(db, 'inv_evidence', id='invev_' + bot.id, investigation_id=investigation,
               claim_id='invclaim_' + bot.id, source_id='invsrc_' + bot.id, relation='supports',
               created_at=stamp)
    insert_row(db, 'inv_answers', id='invans_' + bot.id, investigation_id=investigation,
               body_json=json.dumps({'answer': tag}), effective_as_of=stamp, created_at=stamp)
    insert_row(db, 'inv_media', id='invmedia_' + bot.id, investigation_id=investigation, origin='web',
               local_path='/tmp/media', kind='image', sha256=digest, acquired_at=stamp)
    insert_row(db, 'inv_media_frames', media_id='invmedia_' + bot.id, at_ms=0, path='/tmp/frame.png',
               sha256=digest)
    insert_row(db, 'inv_observations', id='invobs_' + bot.id, investigation_id=investigation, kind='fact',
               text=tag, created_at=stamp)
    insert_row(db, 'inv_query_attempts', id='invqa_' + bot.id, investigation_id=investigation,
               adapter='web', state='done', started_at=stamp)
    insert_row(db, 'inv_stream_cursors', stream_key='stream-' + bot.id, investigation_id=investigation,
               adapter='web', instance='i1', cursor_kind='page', cursor_json='{}', updated_at=stamp)


def _seed_synthesis(db, bot, seed, stamp, tag, digest, conversation, run) -> None:
    """Fixture rows for synthesis manifests, artifacts, plans, sources and effects."""
    manifest = 'syn_' + bot.id
    seed['syn_manifest'] = manifest
    seed['syn_storage_path'] = manifest + '/audio/v001-abcdef12/out.wav'
    insert_row(db, 'syn_manifests', id=manifest, conversation_id=conversation, bot_id=bot.id, run_id=run,
               revision=1, status='committed', language='en', policy='default',
               doc=json.dumps({'summary': tag}), created_at=stamp, updated_at=stamp)
    insert_row(db, 'syn_manifest_revisions', manifest_id=manifest, revision=1, reason='initial',
               doc=json.dumps({'summary': tag}), created_at=stamp)
    insert_row(db, 'syn_artifacts', id='synart_' + bot.id, manifest_id=manifest, kind='audio', version=1,
               status='committed', storage_path=seed['syn_storage_path'], storage_name='out.wav',
               mime='audio/wav', bytes=1, sha256=digest, meta='{}', created_at=stamp)
    plan = 'synplan_' + bot.id
    insert_row(db, 'syn_plans', id=plan, conversation_id=conversation, bot_id=bot.id, run_id=run,
               status='done', approval_scope_hash=digest, doc=json.dumps({'plan': tag}),
               created_at=stamp, updated_at=stamp)
    insert_row(db, 'syn_sources', id='synsrc_' + bot.id, conversation_id=conversation, bot_id=bot.id,
               run_id=run, kind='web', identity='identity-' + bot.id, revision=1, title=tag,
               doc=json.dumps({'source': tag}), created_at=stamp, updated_at=stamp)
    insert_row(db, 'syn_effects', id='syneff_' + bot.id, plan_id=plan, step_id='step-1', kind='tool',
               idempotency_key='effect-key-' + bot.id, status='done', created_at=stamp,
               updated_at=stamp)


def _seed_workflows(db, bot, seed, stamp, tag, digest, conversation, run) -> None:
    """Fixture rows for workflow definitions, runs, nodes, questions and amendments."""
    insert_row(db, 'workflow_definitions', id='def_' + bot.id, name='workflow-' + bot.id,
               description='', active=1, source='fixture', created_at=stamp, updated_at=stamp)
    insert_row(db, 'workflow_revisions', id='rev1_' + bot.id, definition_id='def_' + bot.id, revision=1,
               plan_hash=digest, plan_json='{}', note='', created_by='fixture', created_at=stamp)
    insert_row(db, 'workflow_revisions', id='rev2_' + bot.id, definition_id='def_' + bot.id, revision=2,
               plan_hash=digest, plan_json='{}', note='', created_by='fixture', created_at=stamp)
    workflow = 'wf_' + bot.id
    seed['workflow'] = workflow
    insert_row(db, 'workflow_runs', id=workflow, definition_id='def_' + bot.id, revision_id='rev1_' + bot.id,
               plan_hash=digest, bot_id=bot.id, conversation_id=conversation, origin='user',
               status='succeeded', created_at=stamp, updated_at=stamp)
    insert_row(db, 'workflow_nodes', workflow_run_id=workflow, site_id='site-1',
               instance_key='node-1', kind='tool', status='succeeded', attempt=1)
    insert_row(db, 'workflow_questions', id='wfq_' + bot.id, workflow_run_id=workflow, site_id='site-1',
               instance_key='node-1', question=tag, status='answered', asked_at=stamp, expires_at=stamp)
    insert_row(db, 'workflow_amendment_history', id='wfam_' + bot.id, workflow_run_id=workflow,
               previous_revision_id='rev1_' + bot.id, adopted_revision_id='rev2_' + bot.id,
               previous_attempt_run_id=run, previous_status='succeeded', previous_plan_hash=digest,
               adopted_plan_hash=digest, preview_json=json.dumps({'preview': tag}), nodes_json='[]',
               questions_json='[]', result_json='{}', created_at=stamp)


def _seed_handoffs_and_sessions(store, db, bot, seed, stamp, tag, digest, conversation, message, run) -> None:
    """Fixture rows for code handoffs, media, persona feedback and conversation state."""
    handoff = 'handoff_' + bot.id
    seed['handoff'] = handoff
    insert_row(db, 'code_handoffs', id=handoff, conversation_id=conversation, bot_id=bot.id,
               source_run_id=run, source_user_message_id=message,
               source_assistant_message_id=message, original_request=tag, proposed_brief=tag,
               task_brief=tag, project_root='/home/user/project', project_name='project',
               project_device='1', project_inode=1, git_common_dir='/home/user/project/.git',
               base_commit='a' * 40, status='prepared', created_at=stamp, updated_at=stamp)
    insert_row(db, 'media_jobs', id='media_' + bot.id, run_id=run, conversation_id=conversation,
               kind='image', backend='local', status='succeeded',
               idempotency_key='media-key-' + bot.id,
               requested=tag, created_at=stamp, updated_at=stamp)
    insert_row(db, 'persona_feedback', conversation_id=conversation, message_id=message,
               feedback_version=1, revision=1, rating='helpful', reason=None, updated_at=stamp)
    insert_row(db, 'workspace_sessions', conversation_id=conversation, generation=1, status='active',
               env_fingerprint='env', workspace_dir=str(Path(store.config.state_dir) / 'workspaces' / conversation),
               created_at=stamp, updated_at=stamp)
    insert_row(db, 'conversation_task_state', conversation_id=conversation, revision=1,
               source_high_watermark=0, state_json=json.dumps({'state': tag}), updated_at=stamp)
    insert_row(db, 'conversation_task_state_revisions', conversation_id=conversation, revision=1,
               supersedes_revision=0, source_high_watermark=0, state_json=json.dumps({'state': tag}),
               created_at=stamp)
    insert_row(db, 'conversation_workflow_policies', conversation_id=conversation, mode='off',
               revision=1, updated_at=stamp)
    insert_row(db, 'conversation_runs', conversation_id=conversation, run_id=run, attached_at=stamp)
    insert_row(db, 'assistant_home_conversations', bot_id=bot.id, conversation_id=conversation,
               created_at=stamp)
    insert_row(db, 'tool_allows', bot_id=bot.id, sticky_key='allow-key', created_at=stamp)
    insert_row(db, 'google_mail_grants', bot_id=bot.id, account_id='google-account', granted_at=stamp)
    insert_row(db, 'outlook_mail_grants', bot_id=bot.id, account_id='outlook-account', granted_at=stamp)
    insert_row(db, 'integrations', integration_id='notebooklm-' + bot.id, revision='rev-1',
               title='NotebookLM', transport='in_process', credential_id='', state='operation_authorized',
               enabled=1, created_at=stamp)
    insert_row(db, 'integration_tool_grants', integration_id='notebooklm-' + bot.id, bot_id=bot.id,
               server_tool_name='search', canonical_name='mcp__notebooklm__search',
               schema_revision=digest, granted_at=stamp)
    insert_row(db, 'opencode_session_bindings', binding_key='binding-' + bot.id, bot_id=bot.id,
               route_hash='route', workspace='/tmp/workspace', policy_hash='policy', agent_id='agent',
               session_id='session', updated_at=stamp)
    insert_row(db, 'workspace_specialists', bot_id=bot.id, added_at=stamp)
