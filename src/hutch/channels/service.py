"""Channel I/O supervision only; agent work uses Hutch's existing durable engine."""
from __future__ import annotations

import threading
import uuid

from ..state_snapshot import ExecutionHeld
from . import ChannelError
from .persistence import ChannelBook
from .telegram import ChannelSecrets, Telegram, TelegramFailure


class ChannelService:
    def __init__(self, store, *, secrets=None, transport=Telegram):
        self.book = ChannelBook(store)
        self.secrets = secrets or ChannelSecrets()
        self.transport = transport
        self.owner = 'channel-worker-' + uuid.uuid4().hex
        self.stop_event = threading.Event()
        self.thread = None
        store.register_shutdown(self.close)

    def once(self):
        for entry in self.book.list():
            if not entry['enabled'] or self.stop_event.is_set():
                continue
            connection = self.book.claim(entry['id'],self.owner)
            if connection is None:
                continue
            delay, error = 2, ''
            try:
                secret = self.secrets.get(connection['credential_ref'])
                if not secret:
                    raise ChannelError('The channel token is missing. Disconnect and reconnect this bot.')
                transport = self.transport(secret)
                self.book.queue_replies(connection['id'])
                reply = self.book.take_reply(connection,self.owner)
                if reply:
                    try:
                        message_id = transport.send(reply['sender'],reply['text'])
                    except TelegramFailure as failure:
                        state = 'uncertain' if failure.uncertain else 'pending' if failure.retry_after else 'failed'
                        self.book.finish_reply(reply['id'],state=state,error=str(failure),retry_after=failure.retry_after)
                        raise
                    else:
                        self.book.finish_reply(reply['id'],state='sent',message_id=message_id)
                if self.stop_event.is_set():
                    continue
                self.book.admit(connection['id'])
                updates = transport.updates(connection['cursor'])
                self.book.record_updates(connection,self.owner,updates)
                self.book.admit(connection['id'])
            except TelegramFailure as failure:
                delay, error = failure.retry_after or 60, str(failure)
            except ChannelError as failure:
                delay, error = 60, str(failure)
            except Exception:
                # Never serialize raw network/credential exceptions or response payloads.
                delay, error = 60, 'Channel processing stopped. Review the connection in Hutch.'
            finally:
                self.book.release(connection['id'],self.owner,delay=delay,error=error)

    def start(self):
        if self.thread is not None:
            return
        def loop():
            while not self.stop_event.is_set():
                bus = self.book.store.bus
                seen = {'channels':bus.version('channels')}
                try:
                    self.once()
                    timeout = self.book.next_wakeup()
                except ExecutionHeld:
                    timeout = 30
                except Exception:
                    # A database shutdown cannot become a tight retry loop.
                    timeout = 30
                if not self.stop_event.is_set():
                    bus.wait_any(seen,timeout=timeout)
        self.thread = threading.Thread(target=loop,name='hutch-channels',daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        self.book.store.bus.notify('channels',remote=False)
        if self.thread is not None:
            self.thread.join(timeout=20)
            if self.thread.is_alive():
                raise RuntimeError('Channel transport did not stop before database shutdown.')
