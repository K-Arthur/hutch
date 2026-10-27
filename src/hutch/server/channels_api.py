"""Local-owner channel setup, explicit start, and delivery reconciliation."""
import hashlib
import uuid

from fastapi import HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..channels import ChannelConflict, ChannelError
from ..channels.persistence import ChannelBook
from ..channels.telegram import ChannelSecrets, Telegram
from ..google_calendar import GoogleCalendarError


class ChannelCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=80)
    bot_id: str = Field(min_length=1,max_length=128)
    token: SecretStr
    allowed_senders: list[str] = Field(min_length=1,max_length=32)


class ChannelConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=1,max_length=80)
    bot_id: str = Field(min_length=1,max_length=128)
    allowed_senders: list[str] = Field(min_length=1,max_length=32)


class ChannelEnabled(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool
    expected_revision: int = Field(ge=1)


class ChannelToken(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: SecretStr
    expected_revision: int = Field(ge=1)


class ChannelDiscover(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: SecretStr


class DeliveryReconciliation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    attempts: int = Field(ge=1)
    delivered: bool
    evidence: str = Field(min_length=10,max_length=500)


def install_channel_routes(app, store, engine):
    book, secrets = ChannelBook(store), ChannelSecrets()
    app.state.channel_secrets = secrets

    def fail(error):
        if isinstance(error,KeyError):
            return HTTPException(404,'This channel or delivery no longer exists.')
        return HTTPException(409 if isinstance(error,ChannelConflict) else 422,str(error))

    @app.get('/api/v1/channels')
    def channels(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        return {'contract_version':1,'secret_store_available':secrets.available(), 'connections':book.list(),
                'supported':['telegram_private_text'], 'unavailable':['slack_socket_mode','signed_webhooks']}

    @app.post('/api/v1/channels/telegram',status_code=201)
    def connect(body: ChannelCreate):
        channel_id = 'ch_' + uuid.uuid4().hex[:24]
        token = body.token.get_secret_value()
        if len(token)>128:
            raise HTTPException(422,'Enter a valid Telegram bot token from BotFather.')
        # getMe validates the explicit supplied bot token; no messages are polled or sent.
        try:
            remote = Telegram(token).call('getMe',{})
            secrets.put(channel_id,token)
            try:
                return book.create(name=body.name,bot_id=body.bot_id,allowed_senders=body.allowed_senders,
                    credential_digest=hashlib.sha256(token.encode()).hexdigest(),
                    remote_bot_id=str(remote['id']),channel_id=channel_id)
            except Exception:
                secrets.delete(channel_id)
                raise
        except (ChannelError,GoogleCalendarError) as error:
            raise fail(error) from None

    @app.post('/api/v1/channels/telegram/senders')
    def discover(body: ChannelDiscover, response: Response):
        response.headers['Cache-Control'] = 'no-store'
        try:
            transport = Telegram(body.token.get_secret_value())
            remote = transport.call('getMe',{})
            with store._lock:
                if store._db.execute('SELECT 1 FROM channel_connections WHERE remote_bot_id=? AND enabled=1',
                                     (str(remote['id']),)).fetchone():
                    raise ChannelError('Pause this bot’s existing channel before checking its pending senders.')
            found = {}
            for event in transport.updates(0):
                message = event.get('message',{})
                if not isinstance(message,dict):
                    continue
                sender,chat = message.get('from',{}),message.get('chat',{})
                if not isinstance(sender,dict) or not isinstance(chat,dict):
                    continue
                if (sender.get('is_bot') is False and chat.get('type')=='private'
                        and type(sender.get('id')) is int and sender['id']>0 and sender['id']==chat.get('id')):
                    found[str(sender['id'])] = {'id':str(sender['id']),
                        'name':' '.join(str(sender.get('first_name','')).split())[:80] or 'Telegram account'}
            return {'senders':list(found.values()),'messages_acknowledged':False,'work_started':False}
        except ChannelError as error:
            raise fail(error) from None

    @app.put('/api/v1/channels/{channel_id}/token')
    def reconnect(channel_id: str, body: ChannelToken):
        token = body.token.get_secret_value()
        try:
            current = book.get(channel_id)
            if current is None:
                raise KeyError(channel_id)
            if current['enabled'] or current['revision'] != body.expected_revision:
                raise ChannelConflict('Pause and reload this connection before replacing its token.')
            remote = Telegram(token).call('getMe',{})
            if str(remote['id']) != current['remote_bot_id']:
                raise ChannelError('This token belongs to another Telegram bot. Create a separate connection.')
            credential_ref = 'ch_' + uuid.uuid4().hex[:24]
            secrets.put(credential_ref,token)
            try:
                result = book.reconnect(channel_id,expected_revision=body.expected_revision,
                    remote_bot_id=str(remote['id']),credential_digest=hashlib.sha256(token.encode()).hexdigest(),
                    credential_ref=credential_ref)
            except Exception:
                secrets.delete(credential_ref)
                raise
            if current['credential_ref']:
                secrets.delete(current['credential_ref'])
            return result
        except (ChannelError,GoogleCalendarError,KeyError) as error:
            raise fail(error) from None

    @app.put('/api/v1/channels/{channel_id}/enabled')
    def enable(channel_id: str, body: ChannelEnabled):
        try:
            if body.enabled:
                current = book.get(channel_id)
                if current is None:
                    raise KeyError(channel_id)
                if not current['credential_ref'] or not secrets.get(current['credential_ref']):
                    raise ChannelError('Reconnect this bot before starting the channel.')
            result, runs = book.set_enabled(channel_id,body.enabled,body.expected_revision)
            for run_id in runs:
                engine.stop_run(run_id)
            return result
        except (ChannelError,GoogleCalendarError,KeyError) as error:
            raise fail(error) from None

    @app.put('/api/v1/channels/{channel_id}/configuration')
    def configuration(channel_id: str, body: ChannelConfiguration):
        try:
            return book.update_config(channel_id,**body.model_dump())
        except (ChannelError,KeyError) as error:
            raise fail(error) from None

    @app.delete('/api/v1/channels/{channel_id}')
    def disconnect(channel_id: str, expected_revision: int):
        try:
            current = book.get(channel_id)
            if current is None:
                raise KeyError(channel_id)
            result, runs = book.set_enabled(channel_id,False,expected_revision,forget=True)
            for run_id in runs:
                engine.stop_run(run_id)
            if current['credential_ref']:
                secrets.delete(current['credential_ref'])
            return {'connection':result,'token_removed':True,'history_retained':True}
        except (ChannelError,GoogleCalendarError,KeyError) as error:
            raise fail(error) from None

    @app.get('/api/v1/channels/{channel_id}/deliveries')
    def deliveries(channel_id: str, response: Response):
        response.headers['Cache-Control'] = 'no-store'
        if book.get(channel_id) is None:
            raise HTTPException(404,'This channel no longer exists.')
        return {'contract_version':1,'deliveries':book.deliveries(channel_id)}

    @app.post('/api/v1/channels/{channel_id}/deliveries/{delivery_id}/reconcile')
    def reconcile(channel_id: str, delivery_id: int, body: DeliveryReconciliation):
        try:
            state = book.reconcile(channel_id,delivery_id,**body.model_dump())
            return {'state':state}
        except (ChannelError,KeyError) as error:
            raise fail(error) from None
