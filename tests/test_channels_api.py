"""Owner-only setup via real API/SQLite; provider and vault are synthetic."""
import pytest
from fastapi.testclient import TestClient

from hutch.channels import ChannelConflict
from hutch.channels.persistence import ChannelBook
from hutch.models import Bot
from hutch.server import channels_api
from hutch.server.app import create_app

TOKEN = '123456789:synthetic-not-a-real-token-value'


class Vault:
    def __init__(self): self.values={}
    def available(self):return True
    def put(self,key,value):self.values[key]=value
    def get(self,key):return self.values.get(key)
    def delete(self,key):self.values.pop(key,None)


class FakeTelegram:
    calls=[]
    def __init__(self,token):self.token=token
    def call(self,method,payload):
        self.calls.append(method)
        return {'id':123456789,'is_bot':True}
    def updates(self,offset):
        self.calls.append(('updates',offset))
        return [{'message':{'from':{'id':123,'is_bot':False,'first_name':'Synthetic owner'},
                            'chat':{'id':123,'type':'private'},'text':'not returned'}}]


@pytest.fixture
def channel_api(config,monkeypatch):
    vault=Vault();FakeTelegram.calls=[]
    monkeypatch.setattr(channels_api,'ChannelSecrets',lambda:vault)
    monkeypatch.setattr(channels_api,'Telegram',FakeTelegram)
    app=create_app()
    app.state.channels.stop_event.set()
    monkeypatch.setattr(app.state.engine,'tick',lambda:[])
    bot=app.state.store.create_bot(Bot(name='api-channel-owner',tools=[]))
    with TestClient(app) as client:yield client,app,bot,vault


def create(client,bot):
    response=client.post('/api/v1/channels/telegram',json={'name':'Personal','bot_id':bot.id,
                        'token':TOKEN,'allowed_senders':['123']})
    assert response.status_code==201,response.text
    return response.json()


def test_save_start_pause_disconnect_and_reconnect_are_distinct(channel_api):
    client,app,bot,vault=channel_api
    saved=create(client,bot)
    assert not saved['enabled'] and saved['has_token']
    assert FakeTelegram.calls==['getMe'] and not app.state.store.list_runs()
    assert TOKEN not in client.get('/api/v1/channels').text
    response=client.put(f"/api/v1/channels/{saved['id']}/enabled",json={'enabled':True,'expected_revision':1})
    assert response.status_code==200 and response.json()['enabled']
    assert client.put(f"/api/v1/channels/{saved['id']}/enabled",json={'enabled':False,'expected_revision':1}).status_code==409
    paused=client.put(f"/api/v1/channels/{saved['id']}/enabled",json={'enabled':False,'expected_revision':2}).json()
    disconnected=client.delete(f"/api/v1/channels/{saved['id']}?expected_revision={paused['revision']}")
    assert disconnected.status_code==200 and disconnected.json()['token_removed']
    assert not vault.values
    current=disconnected.json()['connection'];assert not current['has_token']
    assert client.put(f"/api/v1/channels/{saved['id']}/enabled",json={'enabled':True,'expected_revision':current['revision']}).status_code==422
    replaced=client.put(f"/api/v1/channels/{saved['id']}/token",json={'token':TOKEN,'expected_revision':current['revision']})
    assert replaced.status_code==200 and replaced.json()['has_token'] and not replaced.json()['enabled']
    assert len(vault.values)==1


def test_sender_discovery_never_starts_or_acknowledges_work(channel_api):
    client,app,bot,vault=channel_api
    response=client.post('/api/v1/channels/telegram/senders',json={'token':TOKEN})
    assert response.status_code==200,response.text
    assert response.json()=={'senders':[{'id':'123','name':'Synthetic owner'}],
                             'messages_acknowledged':False,'work_started':False}
    assert not vault.values and not app.state.store.list_runs()
    assert not ChannelBook(app.state.store).list()
    saved=create(client,bot)
    client.put(f"/api/v1/channels/{saved['id']}/enabled",json={'enabled':True,'expected_revision':1})
    assert client.post('/api/v1/channels/telegram/senders',json={'token':TOKEN}).status_code==422


def test_failed_registration_cleans_its_new_secret_and_does_not_replace_existing(channel_api):
    client,app,bot,vault=channel_api
    saved=create(client,bot);before=dict(vault.values)
    response=client.post('/api/v1/channels/telegram',json={'name':'Duplicate','bot_id':bot.id,
                        'token':TOKEN,'allowed_senders':['456']})
    assert response.status_code==409
    assert vault.values==before and len(ChannelBook(app.state.store).list())==1
    assert ChannelBook(app.state.store).get(saved['id'])['allowed_senders']=='["123"]'


def test_stale_token_write_cannot_overwrite_current_credential(channel_api,monkeypatch):
    client,app,bot,vault=channel_api;saved=create(client,bot);before=dict(vault.values)
    def conflict(*args,**kwargs):raise ChannelConflict('Synthetic concurrent change')
    monkeypatch.setattr(ChannelBook,'reconnect',conflict)
    result=client.put(f"/api/v1/channels/{saved['id']}/token",json={'token':TOKEN+'changed','expected_revision':1})
    assert result.status_code==409
    assert vault.values==before


def test_channel_validation_does_not_echo_private_payload(channel_api):
    client,_,_,_=channel_api
    response=client.post('/api/v1/channels/telegram',json={'name':'private-name','bot_id':'private-bot',
                        'token':{'private':'credential'},'allowed_senders':[{'private':'sender'}]})
    assert response.status_code==422
    assert 'private-name' not in response.text and 'credential' not in response.text
    assert 'private-bot' not in response.text and 'private-sender' not in response.text


def test_channel_access_edit_requires_paused_current_revision(channel_api):
    client,_,bot,_=channel_api;saved=create(client,bot)
    body={'expected_revision':1,'name':'Updated connection','bot_id':bot.id,'allowed_senders':['456']}
    changed=client.put(f"/api/v1/channels/{saved['id']}/configuration",json=body)
    assert changed.status_code==200 and changed.json()['allowed_senders']==['456']
    assert client.put(f"/api/v1/channels/{saved['id']}/configuration",json=body).status_code==409
    client.put(f"/api/v1/channels/{saved['id']}/enabled",json={'enabled':True,'expected_revision':2})
    body['expected_revision']=3
    assert client.put(f"/api/v1/channels/{saved['id']}/configuration",json=body).status_code==409
