"""Durable channel inbox/outbox, with canonical idempotent run admission.

An inbox row commits before acknowledgement. Canonical message admission has its
own durable idempotency key, closing the crash gap before its run_id is linked.
Unknown sends never become automatic retries: the operator must reconcile them.
"""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import re
import uuid

from ..models import Run, Task, iso, utcnow
from . import ChannelConflict, ChannelError

CHANNEL_ID = re.compile(r"ch_[0-9a-f]{24}\Z")
USER_ID = re.compile(r"[1-9][0-9]{0,19}\Z")


def migrate(db):
    db.execute("""CREATE TABLE IF NOT EXISTS channel_connections (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('telegram')),
        name TEXT NOT NULL, bot_id TEXT NOT NULL,
        credential_digest TEXT NOT NULL UNIQUE, credential_ref TEXT NOT NULL,
        remote_bot_id TEXT NOT NULL UNIQUE,
        allowed_senders TEXT NOT NULL CHECK(json_valid(allowed_senders)),
        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
        revision INTEGER NOT NULL DEFAULT 1, cursor INTEGER NOT NULL DEFAULT 0,
        accept_after TEXT NOT NULL,
        next_poll_at TEXT NOT NULL, lease_owner TEXT NOT NULL DEFAULT '',
        lease_until TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS channel_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT NOT NULL REFERENCES channel_connections(id),
        revision INTEGER NOT NULL, external_id TEXT NOT NULL, sender TEXT NOT NULL,
        text TEXT NOT NULL, content_hash TEXT NOT NULL, received_at TEXT NOT NULL,
        run_id TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'pending'
            CHECK(state IN ('pending','admitted','cancelled')),
        UNIQUE(channel_id, external_id))""")
    db.execute("CREATE INDEX IF NOT EXISTS channel_events_pending ON channel_events(state,id)")
    db.execute("""CREATE TABLE IF NOT EXISTS channel_threads (
        channel_id TEXT NOT NULL REFERENCES channel_connections(id), sender TEXT NOT NULL,
        bot_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL UNIQUE REFERENCES conversations(id),
        PRIMARY KEY(channel_id,sender,bot_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS channel_deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL UNIQUE REFERENCES channel_events(id),
        text TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending'
            CHECK(state IN ('pending','sending','sent','uncertain','failed','cancelled')),
        attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL,
        provider_message_id TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
        reconciled_at TEXT NOT NULL DEFAULT '', reconciliation TEXT NOT NULL DEFAULT '')""")
    from ..durable_changes import install_resources
    install_resources(db, (
        ('channel_connections', 'channels', 'id', ('enabled','revision','last_error'), ('bot_id',)),
        ('channel_events', 'channel_events', 'id', ('state','run_id'), ('channel_id',)),
        ('channel_deliveries', 'channel_deliveries', 'id', ('state',), ('event_id',)),
    ))


def origin_allowed(db, run):
    match = re.fullmatch(r'channel:(ch_[0-9a-f]{24}):([1-9][0-9]*)', run.origin)
    if not match:
        return False
    row = db.execute("SELECT c.enabled,c.revision,c.bot_id,b.doc FROM channel_connections c "
                     "JOIN bots b ON b.id=c.bot_id WHERE c.id=?", (match[1],)).fetchone()
    return bool(row and row['enabled'] and row['revision'] == int(match[2])
                and row['bot_id'] == run.bot_id and json.loads(row['doc']).get('approval_mode', 'ask') == 'ask')


def public(row):
    result = {key: (json.loads(row[key]) if key == 'allowed_senders' else bool(row[key]) if key == 'enabled' else row[key])
            for key in ('id','kind','name','bot_id','allowed_senders','enabled','revision','last_error','created_at')}
    result['contract_version'] = 1
    result['has_token'] = bool(row['credential_ref'])
    return result


class ChannelBook:
    def __init__(self, store):
        self.store = store

    def list(self):
        with self.store._lock:
            return [public(row) for row in self.store._db.execute('SELECT * FROM channel_connections ORDER BY created_at')]

    def get(self, channel_id):
        with self.store._lock:
            row = self.store._db.execute('SELECT * FROM channel_connections WHERE id=?', (channel_id,)).fetchone()
            return dict(row) if row else None

    def create(self, *, name, bot_id, allowed_senders, credential_digest, remote_bot_id, channel_id=None):
        senders = sorted(set(allowed_senders))
        if not senders or len(senders) > 32 or any(not isinstance(x, str) or not USER_ID.fullmatch(x) for x in senders):
            raise ChannelError('Choose 1–32 numeric Telegram user IDs. Usernames are not identities.')
        channel_id = channel_id or 'ch_' + uuid.uuid4().hex[:24]
        if (not CHANNEL_ID.fullmatch(channel_id) or not re.fullmatch('[0-9a-f]{64}', credential_digest)
                or not USER_ID.fullmatch(remote_bot_id)):
            raise ChannelError('Invalid channel identity.')
        name = ' '.join(name.split())
        if not name or len(name) > 80:
            raise ChannelError('Give this connection a name of up to 80 characters.')
        stamp = iso(utcnow())
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            bot = db.execute('SELECT doc FROM bots WHERE id=?', (bot_id,)).fetchone()
            if not bot or json.loads(bot['doc']).get('approval_mode', 'ask') != 'ask':
                raise ChannelError('Choose an assistant that asks before changes. Auto mode cannot receive channel work.')
            if db.execute('SELECT 1 FROM channel_connections WHERE credential_digest=? OR remote_bot_id=?',
                          (credential_digest,remote_bot_id)).fetchone():
                raise ChannelConflict('This Telegram bot is already connected. Manage its existing connection.')
            db.execute("INSERT INTO channel_connections(id,kind,name,bot_id,credential_digest,credential_ref,remote_bot_id,allowed_senders,"
                       "next_poll_at,created_at,accept_after) VALUES (?,'telegram',?,?,?,?,?,?,?,?,?)",
                       (channel_id, name, bot_id, credential_digest, channel_id, remote_bot_id, json.dumps(senders), stamp, stamp, stamp))
        self.store.bus.notify('channels','state')
        return public(self.get(channel_id))

    def reconnect(self, channel_id, *, expected_revision, remote_bot_id, credential_digest, credential_ref):
        if not CHANNEL_ID.fullmatch(credential_ref) or not re.fullmatch('[0-9a-f]{64}',credential_digest):
            raise ChannelError('Invalid channel credential reference.')
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            row = db.execute('SELECT * FROM channel_connections WHERE id=?',(channel_id,)).fetchone()
            if row is None:
                raise KeyError(channel_id)
            if row['revision'] != expected_revision or row['enabled']:
                raise ChannelConflict('Pause and reload this connection before replacing its token.')
            if remote_bot_id != row['remote_bot_id']:
                raise ChannelError('This token belongs to another Telegram bot. Create a separate connection.')
            db.execute("UPDATE channel_connections SET credential_digest=?,credential_ref=?,revision=revision+1,last_error='' WHERE id=?",
                       (credential_digest,credential_ref,channel_id))
        self.store.bus.notify('channels','state')
        return public(self.get(channel_id))

    def update_config(self, channel_id, *, expected_revision, name, bot_id, allowed_senders):
        name = ' '.join(name.split())
        senders = sorted(set(allowed_senders))
        if not name or len(name)>80 or not senders or len(senders)>32 or any(not USER_ID.fullmatch(x) for x in senders):
            raise ChannelError('Choose a name and 1–32 numeric Telegram user IDs.')
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            row = db.execute('SELECT * FROM channel_connections WHERE id=?',(channel_id,)).fetchone()
            if row is None:
                raise KeyError(channel_id)
            if row['enabled'] or row['revision']!=expected_revision:
                raise ChannelConflict('Pause and reload this connection before editing its access.')
            bot = db.execute('SELECT doc FROM bots WHERE id=?',(bot_id,)).fetchone()
            if not bot or json.loads(bot['doc']).get('approval_mode','ask')!='ask':
                raise ChannelError('Choose an assistant that asks before changes.')
            db.execute('UPDATE channel_connections SET name=?,bot_id=?,allowed_senders=?,revision=revision+1 WHERE id=?',
                       (name,bot_id,json.dumps(senders),channel_id))
        self.store.bus.notify('channels','state')
        return public(self.get(channel_id))

    def set_enabled(self, channel_id, enabled, revision, *, forget=False):
        if enabled and forget:
            raise ValueError('Cannot forget an enabled credential')
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            row = db.execute('SELECT * FROM channel_connections WHERE id=?', (channel_id,)).fetchone()
            if row is None:
                raise KeyError(channel_id)
            if row['revision'] != revision:
                raise ChannelConflict('This connection changed. Reload it before continuing.')
            if bool(row['enabled']) == enabled and not forget:
                return public(row), []
            if enabled:
                if not row['credential_ref']:
                    raise ChannelError('Reconnect this bot before starting the channel.')
                bot = db.execute('SELECT doc FROM bots WHERE id=?', (row['bot_id'],)).fetchone()
                if not bot or json.loads(bot['doc']).get('approval_mode', 'ask') != 'ask':
                    raise ChannelError('The assistant must ask before changes before receiving channel work.')
            db.execute('UPDATE channel_connections SET enabled=?,revision=revision+1,next_poll_at=? WHERE id=?',
                       (int(enabled), iso(utcnow()), channel_id))
            if enabled:
                # Telegram dates have second precision. Explicit starts ignore
                # older backlog; ordinary restart/sleep preserves this boundary.
                db.execute('UPDATE channel_connections SET accept_after=? WHERE id=?',
                           (iso(utcnow().replace(microsecond=0)),channel_id))
            if forget:
                db.execute("UPDATE channel_connections SET credential_ref='' WHERE id=?",(channel_id,))
            db.execute("UPDATE channel_events SET state='cancelled' WHERE channel_id=? AND state='pending'", (channel_id,))
            db.execute("UPDATE channel_deliveries SET state='cancelled' WHERE state='pending' AND event_id IN "
                       '(SELECT id FROM channel_events WHERE channel_id=?)', (channel_id,))
            runs = [x[0] for x in db.execute("SELECT id FROM runs WHERE json_extract(doc,'$.origin') LIKE ? "
                    "AND status NOT IN ('succeeded','failed','stopped')", (f'channel:{channel_id}:%',))]
        self.store.bus.notify('channels','state')
        return public(self.get(channel_id)), runs

    def claim(self, channel_id, owner):
        now = utcnow()
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            if db.execute('UPDATE channel_connections SET lease_owner=?,lease_until=? WHERE id=? AND enabled=1 '
                          "AND next_poll_at<=? AND (lease_owner=? OR lease_until<?)",
                          (owner, iso(now + timedelta(seconds=60)), channel_id, iso(now), owner, iso(now))).rowcount != 1:
                return None
            # A lost sender can have crossed the network boundary. Never blindly resend.
            db.execute("UPDATE channel_deliveries SET state='uncertain',error='Sender stopped before confirming delivery.' "
                       "WHERE state='sending' AND event_id IN (SELECT id FROM channel_events WHERE channel_id=?)", (channel_id,))
            return dict(db.execute('SELECT * FROM channel_connections WHERE id=?', (channel_id,)).fetchone())

    def release(self, channel_id, owner, *, delay=2, error=''):
        with self.store._tx() as db:
            db.execute("UPDATE channel_connections SET lease_owner='',lease_until='',next_poll_at=?,last_error=? "
                       'WHERE id=? AND lease_owner=?',
                       (iso(utcnow()+timedelta(seconds=max(1,min(delay,3600)))), error[:200], channel_id, owner))

    def record_updates(self, connection, owner, updates):
        """Offset and accepted text commit together, before Telegram confirms either."""
        from datetime import datetime, timezone
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            row = db.execute('SELECT * FROM channel_connections WHERE id=? AND enabled=1 AND revision=? '
                             'AND lease_owner=? AND lease_until>?',
                             (connection['id'], connection['revision'], owner, iso(utcnow()))).fetchone()
            if row is None:
                raise ChannelConflict('The channel changed while polling. Its response was not admitted.')
            senders = set(json.loads(row['allowed_senders']))
            cursor = row['cursor']
            pending_count = db.execute("SELECT COUNT(*) FROM channel_events WHERE channel_id=? AND state='pending'",
                                       (row['id'],)).fetchone()[0]
            for update in updates:
                update_id = update.get('update_id')
                if type(update_id) is not int or update_id < 0:
                    raise ChannelError('Telegram returned an invalid update identity.')
                cursor = max(cursor, update_id+1)
                message = update.get('message', {})
                if not isinstance(message,dict):
                    continue
                sender = message.get('from', {})
                chat = message.get('chat', {})
                if not isinstance(sender,dict) or not isinstance(chat,dict):
                    continue
                text = message.get('text')
                # Personal text conversations only; no groups, bots, edits, attachments or commands.
                if (sender.get('is_bot') is not False or chat.get('type') != 'private'
                        or type(sender.get('id')) is not int or sender.get('id') != chat.get('id')
                        or str(sender.get('id')) not in senders or not isinstance(text,str)
                        or not text.strip() or len(text)>4000 or text.startswith('/')):
                    continue
                timestamp = message.get('date')
                if type(timestamp) is not int or timestamp < 0:
                    continue
                try:
                    occurred = datetime.fromtimestamp(timestamp, timezone.utc)
                except (ValueError, OverflowError, OSError):
                    continue
                if iso(occurred) < row['accept_after'] or occurred > utcnow()+timedelta(minutes=5):
                    continue
                digest = hashlib.sha256(json.dumps([str(sender['id']),text],ensure_ascii=False).encode()).hexdigest()
                prior = db.execute('SELECT content_hash FROM channel_events WHERE channel_id=? AND external_id=?',
                                   (row['id'], str(update_id))).fetchone()
                if prior and prior['content_hash'] != digest:
                    raise ChannelConflict('Telegram reused an update identity with different content.')
                if not prior and update_id < row['cursor']:
                    continue  # The committed cursor is also a replay floor after retention cleanup.
                if not prior:
                    pending_count += 1
                    if pending_count > 100:
                        raise ChannelError('The channel inbox is full. Pending work must drain before more messages are acknowledged.')
                db.execute('INSERT OR IGNORE INTO channel_events(channel_id,revision,external_id,sender,text,content_hash,received_at) '
                           'VALUES (?,?,?,?,?,?,?)',
                           (row['id'],row['revision'],str(update_id),str(sender['id']),text,digest,iso(utcnow())))
            db.execute('UPDATE channel_connections SET cursor=? WHERE id=?', (cursor,row['id']))

    def admit(self, channel_id):
        row = self.get(channel_id)
        if row is None or not row['enabled']:
            return 0
        bot = self.store.get_bot(row['bot_id'])
        if bot is None or bot.paused or bot.approval_mode.value != 'ask':
            return 0
        with self.store._lock:
            pending = [dict(x) for x in self.store._db.execute("SELECT * FROM channel_events WHERE channel_id=? "
                        "AND revision=? AND state='pending' ORDER BY id LIMIT 1",(channel_id,row['revision']))]
            live = self.store._db.execute("SELECT 1 FROM channel_events e JOIN runs r ON r.id=e.run_id "
                        "WHERE e.channel_id=? AND r.status NOT IN ('succeeded','failed','stopped','skipped','outcome_unknown')",(channel_id,)).fetchone()
            recent = self.store._db.execute("SELECT COUNT(*) FROM channel_events e JOIN runs r ON r.id=e.run_id "
                        'WHERE e.channel_id=? AND r.created_at>?',
                        (channel_id,iso(utcnow()-timedelta(hours=1)))).fetchone()[0]
        if live or recent >= 20:
            return 0
        admitted = 0
        for event in pending:
            with self.store._tx() as db:
                self.store._assert_execution_ready(db)
                thread = db.execute('SELECT conversation_id FROM channel_threads WHERE channel_id=? AND sender=? AND bot_id=?',
                                    (channel_id,event['sender'],bot.id)).fetchone()
                conversation_id = thread[0] if thread else 'conv_' + uuid.uuid4().hex[:12]
                if not thread:
                    stamp = iso(utcnow())
                    db.execute('INSERT INTO conversations(id,bot_id,title,created_at,updated_at) VALUES (?,?,?,?,?)',
                               (conversation_id,bot.id,f"Telegram · {row['name']} · {event['sender']}",stamp,stamp))
                    db.execute('INSERT INTO channel_threads VALUES (?,?,?,?)', (channel_id,event['sender'],bot.id,conversation_id))
            run_id, _ = self.store.submit_conversation_message(conversation_id,event['text'],
                Run(bot_id=bot.id,prompt=event['text'],origin=f"channel:{channel_id}:{row['revision']}"),
                Task(bot_id=bot.id,prompt=event['text'],kind='channel'),
                idem_key=f"channel-event:{event['id']}",request_hash=event['content_hash'])
            with self.store._tx() as db:
                db.execute("UPDATE channel_events SET run_id=?,state='admitted' WHERE id=? AND state='pending'", (run_id,event['id']))
            admitted += 1
        return admitted

    def queue_replies(self, channel_id):
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            events = db.execute("SELECT e.id,e.run_id,r.status FROM channel_events e JOIN runs r ON r.id=e.run_id "
                "JOIN channel_connections c ON c.id=e.channel_id AND c.enabled=1 AND c.revision=e.revision "
                "WHERE e.channel_id=? AND e.state='admitted' AND r.status IN ('succeeded','failed','stopped','skipped','outcome_unknown') "
                "AND NOT EXISTS (SELECT 1 FROM channel_deliveries d WHERE d.event_id=e.id) LIMIT 20",(channel_id,)).fetchall()
            for event in events:
                answer = db.execute("SELECT content FROM messages WHERE run_id=? AND role='assistant' AND incomplete=0 "
                                    'ORDER BY seq DESC LIMIT 1',(event['run_id'],)).fetchone()
                text = answer[0] if event['status']=='succeeded' and answer and answer[0].strip() else 'This task needs attention. Open Hutch to review its status.'
                if len(text)>3500:
                    text = text[:3400]+'\n\n[Reply shortened. Open Hutch for the full answer and artifacts.]'
                db.execute('INSERT INTO channel_deliveries(event_id,text,next_attempt_at) VALUES (?,?,?)',
                           (event['id'],text,iso(utcnow())))

    def take_reply(self, connection, owner):
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            row = db.execute("SELECT d.*,e.sender FROM channel_deliveries d JOIN channel_events e ON e.id=d.event_id "
                "JOIN channel_connections c ON c.id=e.channel_id WHERE c.id=? AND c.enabled=1 AND c.revision=? "
                "AND e.revision=c.revision AND c.lease_owner=? AND c.lease_until>? "
                "AND d.state='pending' AND d.next_attempt_at<=? ORDER BY d.id LIMIT 1",
                (connection['id'],connection['revision'],owner,iso(utcnow()),iso(utcnow()))).fetchone()
            if row is None:
                return None
            db.execute("UPDATE channel_deliveries SET state='sending',attempts=attempts+1 WHERE id=?",(row['id'],))
            return dict(row)

    def finish_reply(self, delivery_id, *, state, message_id='', error='', retry_after=0):
        if state not in ('sent','uncertain','failed','pending'):
            raise ValueError('Invalid delivery outcome')
        with self.store._tx() as db:
            db.execute("UPDATE channel_deliveries SET state=?,provider_message_id=?,error=?,next_attempt_at=? "
                       "WHERE id=? AND state='sending'",(state,message_id,error[:200],
                       iso(utcnow()+timedelta(seconds=max(1,min(retry_after,3600)))),delivery_id))

    def deliveries(self, channel_id):
        with self.store._lock:
            return [dict(row) for row in self.store._db.execute("SELECT d.id,d.state,d.attempts,d.provider_message_id,"
                "d.error,d.reconciled_at,e.run_id FROM channel_deliveries d JOIN channel_events e ON e.id=d.event_id "
                'WHERE e.channel_id=? ORDER BY d.id DESC LIMIT 50',(channel_id,))]

    def next_wakeup(self):
        from datetime import datetime
        with self.store._lock:
            row = self.store._db.execute("SELECT MIN(CASE WHEN lease_until>next_poll_at THEN lease_until ELSE next_poll_at END) "
                                         'FROM channel_connections WHERE enabled=1').fetchone()
        if not row[0]:
            return 300.0
        return max(.1,min(300.0,(datetime.fromisoformat(row[0])-utcnow()).total_seconds()))

    def reconcile(self, channel_id, delivery_id, *, attempts, delivered, evidence):
        evidence = evidence.strip()
        if not 10 <= len(evidence) <= 500:
            raise ChannelError('Record 10–500 characters of independent delivery evidence.')
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            row = db.execute('SELECT d.*,e.revision,c.revision AS current_revision,c.enabled '
                'FROM channel_deliveries d JOIN channel_events e ON e.id=d.event_id '
                'JOIN channel_connections c ON c.id=e.channel_id WHERE d.id=? AND c.id=?',
                (delivery_id,channel_id)).fetchone()
            if row is None:
                raise KeyError(delivery_id)
            if row['state'] != 'uncertain' or row['attempts'] != attempts:
                raise ChannelConflict('This delivery changed. Reload its current outcome.')
            state = 'sent' if delivered else 'pending' if row['enabled'] and row['revision']==row['current_revision'] else 'cancelled'
            db.execute('UPDATE channel_deliveries SET state=?,reconciled_at=?,reconciliation=?,error=?,next_attempt_at=? WHERE id=?',
                (state,iso(utcnow()),evidence,'',iso(utcnow()),delivery_id))
            db.execute('UPDATE channel_connections SET next_poll_at=? WHERE id=?',(iso(utcnow()),channel_id))
        self.store.bus.notify('channels','state')
        return state
