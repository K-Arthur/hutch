"""Real SQLite channel boundaries; fake Telegram transport never calls a model/network."""
from datetime import timedelta
import hashlib
import io
import json
import urllib.error

import pytest

from hutch.channels import ChannelConflict, ChannelError
from hutch.channels.persistence import ChannelBook
from hutch.channels.service import ChannelService
from hutch.channels.telegram import Telegram, TelegramFailure
from hutch.models import ApprovalMode, Bot, Event, EventType, Run, RunStatus, Task, iso, utcnow
from hutch.store import Store

TOKEN = '123456789:' + 'synthetic-not-a-real-token-value'


@pytest.fixture
def channel(store):
    bot = store.create_bot(Bot(name='channel-reader',tools=[],approval_mode=ApprovalMode.ask))
    book = ChannelBook(store)
    row = book.create(name='Personal Telegram',bot_id=bot.id,allowed_senders=['123','456'],
                      credential_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),remote_bot_id='123456789')
    row, _ = book.set_enabled(row['id'],True,row['revision'])
    return book, bot, row


def update(identity=1, sender=123, text='Read this synthetic message.'):
    return {'update_id':identity, 'message':{'date':int((utcnow()+timedelta(seconds=1)).timestamp()),
        'from':{'id':sender,'is_bot':False},'chat':{'id':sender,'type':'private'},'text':text}}


def ingest(channel, updates=None):
    book, bot, row = channel
    claimed = book.claim(row['id'],'test-owner')
    assert claimed
    book.record_updates(claimed,'test-owner',updates if updates is not None else [update()])
    return claimed


def run_for(channel):
    book, _, row = channel
    with book.store._lock:
        run_id = book.store._db.execute('SELECT run_id FROM channel_events WHERE channel_id=? ORDER BY id LIMIT 1',
                                        (row['id'],)).fetchone()[0]
    return book.store.get_run(run_id)


def complete(channel, text='Verified synthetic answer.'):
    run = run_for(channel); store = channel[0].store
    run = store.claim_run(run.id,'worker',30)
    store.transition_run(run.id,RunStatus.running,fence=run.fence)
    store.append_event(Event(run_id=run.id,owner_fence=run.fence,type=EventType.message,
                             data={'role':'assistant','content':text}))
    store.transition_run(run.id,RunStatus.succeeded,fence=run.fence)
    store.flush_events()


def test_channel_duplicate_restart_and_crash_gap_admit_once(channel, config, monkeypatch):
    book, bot, row = channel
    ingest(channel,[update(),update()])
    assert book.get(row['id'])['cursor']==2
    original = book.store.submit_conversation_message
    def interrupted(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('Synthetic crash after canonical admission')
    with monkeypatch.context() as patch:
        patch.setattr(book.store,'submit_conversation_message',interrupted)
        with pytest.raises(RuntimeError,match='Synthetic crash'):
            book.admit(row['id'])
    # The canonical run may already be queued, even though its inbox link is absent.
    assert book.admit(row['id'])==1
    run = run_for(channel)
    assert run.origin==f"channel:{row['id']}:{row['revision']}"
    assert len(book.store.list_conversation_messages(run.conversation_id))==1
    assert len(book.store.list_runs(bot.id))==1
    other = Store(config)
    try:
        assert ChannelBook(other).admit(row['id'])==0
        assert ChannelBook(other).get(row['id'])['cursor']==2
    finally:
        other.close()


@pytest.mark.parametrize('change', ['unknown_sender','group','bot','command','attachment','old','future','huge_date','long'])
def test_channel_ignores_unauthorized_or_unsupported_input_but_commits_offset(channel,change):
    event=update()
    if change=='unknown_sender': event=update(sender=999)
    elif change=='group': event['message']['chat']['type']='group'
    elif change=='bot': event['message']['from']['is_bot']=True
    elif change=='command': event['message']['text']='/approve all'
    elif change=='attachment': event['message'].pop('text');event['message']['photo']=[{'file_id':'fixture'}]
    elif change=='old': event['message']['date']=1
    elif change=='future': event['message']['date']=int((utcnow()+timedelta(days=1)).timestamp())
    elif change=='huge_date': event['message']['date']=10**100
    elif change=='long': event['message']['text']='x'*4001
    ingest(channel,[event])
    book,_,row=channel
    assert book.get(row['id'])['cursor']==2
    assert book.admit(row['id'])==0
    assert not book.store.list_runs()


def test_changed_duplicate_refuses_without_advancing_cursor(channel):
    claimed=ingest(channel)
    book,_,row=channel
    with pytest.raises(ChannelConflict,match='different content'):
        book.record_updates(claimed,'test-owner',[update(2),update(text='Conflicting retry')])
    assert book.get(row['id'])['cursor']==2
    assert book.admit(row['id'])==1
    assert len(book.store.list_runs())==1


def test_channel_threads_cannot_become_main_chat_and_senders_are_isolated(channel):
    book,bot,row=channel
    ingest(channel,[update(),update(2,sender=456)])
    book.admit(row['id']);first=run_for(channel);complete(channel)
    book.admit(row['id'])
    runs=book.store.list_runs(bot.id)
    assert len(runs)==2 and len({r.conversation_id for r in runs})==2
    with pytest.raises(ValueError,match='active direct'):
        book.store.ensure_assistant_home_conversation(bot.id,first.conversation_id)
    home,_=book.store.ensure_assistant_home_conversation(bot.id)
    assert home not in {r.conversation_id for r in runs}
    assert all(not r.conversation_context for r in runs)


def test_pause_stops_admission_and_claim_and_fences_late_poll(channel):
    book,bot,row=channel;claimed=ingest(channel)
    book.admit(row['id']);run=run_for(channel)
    changed,runs=book.set_enabled(row['id'],False,row['revision'])
    assert run.id in runs and not changed['enabled']
    with pytest.raises(ChannelConflict):book.record_updates(claimed,'test-owner',[update(2)])
    assert book.store.claim_run(run.id,'worker',30) is None
    assert book.store.get_run(run.id).exit_reason=='channel_authority_revoked'
    with pytest.raises(ChannelConflict):book.set_enabled(row['id'],True,row['revision'])


def test_auto_mode_revokes_queued_channel_authority(channel):
    book,bot,row=channel;ingest(channel);book.admit(row['id']);run=run_for(channel)
    book.store.upsert_bot(bot.model_copy(update={'approval_mode':ApprovalMode.auto}))
    assert book.store.claim_run(run.id,'worker',30) is None
    with pytest.raises(ChannelError,match='asks before changes'):
        book.create(name='Unsafe',bot_id=bot.id,allowed_senders=['123'],credential_digest='f'*64,remote_bot_id='555555555')


def test_connection_has_no_secret_and_saving_does_not_start_receiving(store):
    bot=store.create_bot(Bot(name='not-started',tools=[]));book=ChannelBook(store)
    row=book.create(name='Personal',bot_id=bot.id,allowed_senders=['123'],credential_digest='a'*64,remote_bot_id='222222222')
    assert not row['enabled'] and 'credential_digest' not in row
    assert book.claim(row['id'],'worker') is None
    with pytest.raises(ChannelConflict):
        book.create(name='Duplicate',bot_id=bot.id,allowed_senders=['123'],credential_digest='a'*64,remote_bot_id='222222222')


def test_outbox_crash_is_uncertain_and_needs_evidence_to_resend(channel):
    book,_,row=channel;claimed=ingest(channel);book.admit(row['id']);complete(channel)
    book.queue_replies(row['id']);book.queue_replies(row['id'])
    reply=book.take_reply(claimed,'test-owner')
    assert reply['text']=='Verified synthetic answer.'
    assert book.take_reply(claimed,'test-owner') is None
    # Same owner reclaims after losing the previous outcome: no automatic duplicate send.
    book.claim(row['id'],'test-owner')
    delivery=book.deliveries(row['id'])[0]
    assert delivery['state']=='uncertain' and delivery['attempts']==1
    assert book.take_reply(claimed,'test-owner') is None
    with pytest.raises(ChannelError,match='independent'):
        book.reconcile(row['id'],delivery['id'],attempts=1,delivered=False,evidence='guess')
    assert book.reconcile(row['id'],delivery['id'],attempts=1,delivered=False,
                          evidence='Checked Telegram history; no reply was delivered.')=='pending'
    reply=book.take_reply(claimed,'test-owner');book.finish_reply(reply['id'],state='sent',message_id='17')
    assert book.deliveries(row['id'])[0]['provider_message_id']=='17'
    assert book.take_reply(claimed,'test-owner') is None
    with pytest.raises(ChannelConflict):
        book.reconcile(row['id'],delivery['id'],attempts=1,delivered=True,evidence='Stale confirmation')


def test_two_supervisors_cannot_poll_or_send_same_connection(channel,config):
    book,_,row=channel;claimed=ingest(channel)
    other=Store(config)
    try:
        assert ChannelBook(other).claim(row['id'],'second-owner') is None
    finally:other.close()


def test_service_respects_provider_backoff_without_losing_delivery(channel):
    book,_,row=channel;ingest(channel);book.admit(row['id']);complete(channel)
    book.release(row['id'],'test-owner')
    with book.store._tx() as db:db.execute("UPDATE channel_connections SET next_poll_at='' WHERE id=?",(row['id'],))
    class Secrets:
        def get(self,_):return TOKEN
    class Limited:
        def __init__(self,_):pass
        def send(self,*_):raise TelegramFailure(retry_after=120,status=429)
    service=ChannelService(book.store,secrets=Secrets(),transport=Limited)
    service.once()
    assert book.deliveries(row['id'])[0]['state']=='pending'
    assert book.get(row['id'])['next_poll_at']>iso(utcnow()+timedelta(seconds=100))
    service.once()
    assert book.deliveries(row['id'])[0]['attempts']==1


class Response(io.BytesIO):
    def __init__(self,payload,status=200):super().__init__(json.dumps(payload).encode());self.code=status


class Opener:
    def __init__(self,result):self.result=result;self.requests=[]
    def open(self,request,timeout):
        self.requests.append(request)
        if isinstance(self.result,Exception):raise self.result
        return self.result


@pytest.mark.parametrize('result,uncertain,delay',[
    (Response({'ok':False,'description':TOKEN},401),False,0),
    (Response({'ok':False,'parameters':{'retry_after':42}},429),False,42),
    (Response({'ok':False,'description':TOKEN},503),True,0),
    (Response({'ok':False,'error_code':500,'description':TOKEN},200),True,0),
    (Response({'ok':True,'result':{'message_id':9,'chat':{'id':999}}}),True,0),
    (urllib.error.URLError(TOKEN),True,0),
])
def test_send_outcomes_and_errors_are_secret_free(result,uncertain,delay):
    with pytest.raises(TelegramFailure) as caught:Telegram(TOKEN,opener=Opener(result)).send('123','fixture')
    assert caught.value.uncertain==uncertain and caught.value.retry_after==delay
    assert TOKEN not in str(caught.value) and TOKEN not in repr(caught.value)


def test_telegram_uses_bounded_poll_and_plain_protected_reply():
    opener=Opener(Response({'ok':True,'result':[]}));client=Telegram(TOKEN,opener=opener)
    assert client.updates(19)==[]
    payload=json.loads(opener.requests[0].data)
    assert payload=={'offset':19,'timeout':0,'limit':50,'allowed_updates':['message']}
    opener.result=Response({'ok':True,'result':{'message_id':88,'chat':{'id':123}}})
    assert client.send('123','<b>literal</b>')=='88'
    payload=json.loads(opener.requests[-1].data)
    assert 'parse_mode' not in payload and payload['protect_content'] is True


@pytest.mark.parametrize('cancel',[False,True])
def test_channel_uses_canonical_engine_tools_and_exact_owner_approval(channel,config,cancel):
    import time
    from pathlib import Path
    from hutch.engine import Engine
    from hutch.models import ApprovalStatus
    book,bot,row=channel
    bot=book.store.upsert_bot(bot.model_copy(update={'tools':['files'],'model':'mock/demo'}))
    claimed=ingest(channel,[update(text='Write a synthetic report.')]);book.admit(row['id'])
    run=run_for(channel);engine=Engine(config,book.store,light=True)
    engine.dispatch_pending()
    deadline=time.monotonic()+8
    try:
        while not book.store.pending_approvals(bot.id) and time.monotonic()<deadline:time.sleep(.01)
        approvals=book.store.pending_approvals(bot.id)
        assert len(approvals)==1
        approval=approvals[0]
        assert approval.run_id==run.id and approval.action_hash and approval.tool=='files' and 'report.md' in approval.action
        assert not book.deliveries(row['id'])
        if cancel:
            _,runs=book.set_enabled(row['id'],False,row['revision'])
            for run_id in runs:engine.stop_run(run_id)
        else:
            _,outcome=book.store.decide_approval(approval.id,ApprovalStatus.approved,'fixture-owner',expected_hash=approval.action_hash)
            assert outcome=='won'
        while engine.active_count and time.monotonic()<deadline:time.sleep(.01)
        assert not engine.active_count
        finished=book.store.get_run(run.id)
        if cancel:
            assert finished.status is RunStatus.stopped
            assert not (Path(finished.workspace)/'report.md').exists()
            book.queue_replies(row['id']);assert not book.deliveries(row['id'])
        else:
            assert finished.status is RunStatus.succeeded
            assert 'Deterministic scenario output' in (Path(finished.workspace)/'report.md').read_text()
            assert any(action['tool']=='write_file' and action['status']=='done' for action in book.store.list_actions(run.id))
            book.queue_replies(row['id']);reply=book.take_reply(claimed,'test-owner')
            assert reply and 'Test scenario finished' in reply['text']
            book.finish_reply(reply['id'],state='sent',message_id='fixture-message-1')
            assert book.store.verify_chain(run.id)['ok']
    finally:engine.shutdown()


def test_restored_channel_never_reuses_source_vault_or_resends_old_work(channel,config,tmp_path):
    from hutch.config import hutchConfig
    from hutch.state_snapshot import backup,restore,ExecutionHeld
    book,bot,row=channel;claimed=ingest(channel);book.admit(row['id']);complete(channel)
    book.queue_replies(row['id']);book.take_reply(claimed,'test-owner')
    snapshot=tmp_path/'snapshot';destination=tmp_path/'restored'
    backup(config,snapshot);report=restore(snapshot,destination)
    restored=Store(hutchConfig(destination))
    try:
        other=ChannelBook(restored)
        assert report['counts']['channels']==1
        assert not other.list()[0]['enabled'] and not other.list()[0]['has_token']
        assert other.deliveries(row['id'])[0]['state']=='uncertain'
        with pytest.raises(ExecutionHeld):other.claim(row['id'],'restored-owner')
        restored.activate_restoration(report['id'],'Verified isolated restored fixture; source remains separate.')
        assert other.claim(row['id'],'restored-owner') is None
        assert other.admit(row['id'])==0
        assert book.get(row['id'])['enabled'] and book.get(row['id'])['credential_ref']
        assert book.deliveries(row['id'])[0]['state']=='sending'
    finally:restored.close()


def test_removing_assistant_disables_its_channel_without_erasing_delivery_history(channel):
    book,bot,row=channel;ingest(channel);book.admit(row['id']);run=run_for(channel)
    assert book.store.delete_bot(bot.id)
    assert not book.get(row['id'])['enabled']
    assert book.store.claim_run(run.id,'worker',30) is None
    assert book.store.get_conversation(run.conversation_id)


def test_malformed_message_does_not_poison_valid_update_cursor(channel):
    ingest(channel,[{'update_id':1,'message':None},{'update_id':2,'message':{'from':None}},update(3)])
    book,_,row=channel
    assert book.get(row['id'])['cursor']==4 and book.admit(row['id'])==1


def test_changing_assistant_does_not_transfer_previous_channel_context(channel):
    book,bot,row=channel;ingest(channel);book.admit(row['id']);old_run=run_for(channel);complete(channel)
    paused,_=book.set_enabled(row['id'],False,row['revision'])
    other=book.store.create_bot(Bot(name='other-channel-assistant',tools=[]))
    changed=book.update_config(row['id'],expected_revision=paused['revision'],name='New assignment',
                               bot_id=other.id,allowed_senders=['123'])
    enabled,_=book.set_enabled(row['id'],True,changed['revision'])
    book.release(row['id'],'test-owner',delay=1)
    with book.store._tx() as db:db.execute("UPDATE channel_connections SET next_poll_at='' WHERE id=?",(row['id'],))
    ingest((book,other,enabled),[update(2,text='A separate assignment.')]);book.admit(row['id'])
    new_run=book.store.list_runs(other.id)[0]
    assert new_run.conversation_id!=old_run.conversation_id and not new_run.conversation_context
    assert book.store.get_conversation(old_run.conversation_id)['bot_id']==bot.id
    with pytest.raises(ChannelConflict):
        book.update_config(row['id'],expected_revision=enabled['revision'],name='Unsafe live edit',
                           bot_id=bot.id,allowed_senders=['456'])


def test_full_inbox_applies_backpressure_without_acknowledging_lost_work(channel):
    book,_,row=channel;claimed=ingest(channel,[update(i) for i in range(1,51)])
    book.record_updates(claimed,'test-owner',[update(i) for i in range(51,101)])
    with pytest.raises(ChannelError,match='inbox is full'):
        book.record_updates(claimed,'test-owner',[update(101)])
    assert book.get(row['id'])['cursor']==101
    with book.store._lock:
        assert book.store._db.execute('SELECT COUNT(*) FROM channel_events').fetchone()[0]==100


def test_channel_migration_is_additive_backed_up_and_replayable(config):
    import sqlite3
    from contextlib import closing
    from hutch.store import _migrate_81,SCHEMA_VERSION
    original=Store(config)
    bot=original.create_bot(Bot(name='before-channels',tools=[]))
    original.close()
    with closing(sqlite3.connect(config.db_path)) as legacy:
        for table in ('channel_deliveries','channel_threads','channel_events','channel_connections'):
            legacy.execute('DROP TABLE '+table)
        legacy.execute('PRAGMA user_version=80');legacy.commit()
    upgraded=Store(config)
    try:
        assert upgraded.schema_version==SCHEMA_VERSION
        assert upgraded.get_bot(bot.id).name=='before-channels'
        with upgraded._tx() as db:
            _migrate_81(db)
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        backup=config.db_path.with_suffix('.db.bak-v80')
        assert backup.is_file()
        with closing(sqlite3.connect(backup)) as before:
            assert before.execute('PRAGMA user_version').fetchone()[0]==80
            assert before.execute("SELECT 1 FROM sqlite_master WHERE name='channel_connections'").fetchone() is None
    finally:upgraded.close()


def test_explicit_restart_ignores_paused_backlog_but_accepts_start_second(channel,monkeypatch):
    from datetime import datetime
    book,bot,row=channel
    started=datetime.fromisoformat(book.get(row['id'])['accept_after'])
    first=update();first['message']['date']=int(started.timestamp())
    ingest(channel,[first])
    paused,_=book.set_enabled(row['id'],False,row['revision'])
    later=utcnow()+timedelta(minutes=2)
    with monkeypatch.context() as patch:
        patch.setattr('hutch.channels.persistence.utcnow',lambda:later)
        enabled,_=book.set_enabled(row['id'],True,paused['revision'])
        claimed=book.claim(row['id'],'test-owner');assert claimed
        old=update(2,text='Sent while paused');old['message']['date']=int(started.timestamp())
        new=update(3,text='Sent in the start second');new['message']['date']=int(later.timestamp())
        book.record_updates(claimed,'test-owner',[old,new]);assert book.admit(row['id'])==1
    assert book.store.list_runs(bot.id)[0].prompt=='Sent in the start second'
    assert book.get(row['id'])['cursor']==4


def test_absent_delivery_cannot_retry_after_channel_revocation(channel):
    book,_,row=channel;claimed=ingest(channel);book.admit(row['id']);complete(channel)
    book.queue_replies(row['id']);book.take_reply(claimed,'test-owner');book.claim(row['id'],'test-owner')
    delivery=book.deliveries(row['id'])[0]
    book.set_enabled(row['id'],False,row['revision'])
    assert book.reconcile(row['id'],delivery['id'],attempts=1,delivered=False,
                          evidence='Independent synthetic history confirms the reply is absent.')=='cancelled'
    assert book.take_reply(claimed,'test-owner') is None
