"""Durable delivery outbox shared by channel replies and owner notifications.

One row per send, one lease, one sender. Reply deliveries point at the inbound event
they answer; notification deliveries point at the durable alert they announce. Exactly
one of the two references is present, which is what keeps a single state machine,
backoff and reconciliation path for both.
"""
from __future__ import annotations

import json
from datetime import timedelta

from ..models import iso, utcnow
from ..notifications import render_notification
from . import ChannelConflict, ChannelError


class OutboxMixin:
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
                db.execute('INSERT INTO channel_deliveries(channel_id,event_id,text,next_attempt_at) VALUES (?,?,?,?)',
                           (channel_id,event['id'],text,iso(utcnow())))

    def queue_notifications(self, channel_id, *, max_age_hours=24, limit=3):
        """Queue this connection's own assistant notifications at most once each.

        A notification is queued only while it is recent and still true: a needs-you
        approval that was already decided is not sent. ``notification_id`` is unique in
        the outbox, so two cycles (or two supervisors) cannot duplicate a delivery.
        """
        cutoff = iso(utcnow() - timedelta(hours=max(1, min(max_age_hours, 168))))
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            connection = db.execute('SELECT * FROM channel_connections WHERE id=? AND enabled=1',
                                    (channel_id,)).fetchone()
            if connection is None:
                return 0
            bot = db.execute('SELECT doc FROM bots WHERE id=?', (connection['bot_id'],)).fetchone()
            if bot is None:
                return 0
            doc = json.loads(bot['doc'])
            label = str(doc.get('display_name') or doc.get('name') or connection['bot_id'])
            rows = [dict(row) for row in db.execute(
                "SELECT n.* FROM notifications n WHERE n.bot_id=? AND n.created_at>=? "
                "AND NOT EXISTS (SELECT 1 FROM channel_deliveries d WHERE d.notification_id=n.id) "
                "AND (n.kind != 'approval_needs_you' OR EXISTS ("
                "SELECT 1 FROM approvals a WHERE a.id=n.subject_id AND a.status='pending')) "
                'ORDER BY n.created_at, n.id LIMIT ?', (connection['bot_id'], cutoff, max(1, min(limit, 10))))]
            queued = 0
            for row in rows:
                db.execute('INSERT INTO channel_deliveries(channel_id,notification_id,text,next_attempt_at) '
                           'VALUES (?,?,?,?)',
                           (channel_id, row['id'], render_notification(row, label), iso(utcnow())))
                queued += 1
            return queued

    def take_notification(self, connection, owner):
        """Lease one queued notification delivery to the caller's supervisor cycle.

        The alert goes to the person whose message started the work when that person is
        an allowed sender, otherwise to the first configured sender. Both are inside the
        connection's reviewed allowlist; the alert never widens who can be reached.
        """
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            row = db.execute("SELECT d.*,n.kind,n.bot_id,n.subject_kind,n.subject_id,n.detail,"
                "n.created_at AS notified_at,c.allowed_senders,"
                "(SELECT e.sender FROM channel_events e WHERE e.channel_id=d.channel_id "
                "AND e.state='admitted' AND e.run_id=coalesce("
                "(SELECT a.run_id FROM approvals a WHERE a.id=CASE WHEN n.subject_kind='approval' "
                "THEN n.subject_id ELSE '' END),"
                "CASE WHEN n.subject_kind='run' THEN n.subject_id ELSE '' END) "
                "ORDER BY e.id LIMIT 1) AS origin_sender "
                'FROM channel_deliveries d JOIN notifications n ON n.id=d.notification_id '
                'JOIN channel_connections c ON c.id=d.channel_id '
                'WHERE d.channel_id=? AND c.enabled=1 AND c.lease_owner=? AND c.lease_until>? '
                "AND d.state='pending' AND d.next_attempt_at<=? ORDER BY d.id LIMIT 1",
                (connection['id'],owner,iso(utcnow()),iso(utcnow()))).fetchone()
            if row is None:
                return None
            db.execute("UPDATE channel_deliveries SET state='sending',attempts=attempts+1 WHERE id=?",(row['id'],))
            result = dict(row)
            senders = json.loads(row['allowed_senders'])
            origin = str(row['origin_sender'] or '')
            result['sender'] = origin if origin in senders else (senders[0] if senders else '')
            return result

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
                "d.error,d.reconciled_at,coalesce(e.run_id,'') AS run_id,coalesce(n.kind,'') AS notification_kind "
                'FROM channel_deliveries d LEFT JOIN channel_events e ON e.id=d.event_id '
                'LEFT JOIN notifications n ON n.id=d.notification_id '
                'WHERE d.channel_id=? ORDER BY d.id DESC LIMIT 50',(channel_id,))]

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
            row = db.execute('SELECT d.*,coalesce(e.revision,c.revision) AS revision,c.revision AS current_revision,c.enabled '
                'FROM channel_deliveries d LEFT JOIN channel_events e ON e.id=d.event_id '
                'JOIN channel_connections c ON c.id=d.channel_id WHERE d.id=? AND c.id=?',
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
