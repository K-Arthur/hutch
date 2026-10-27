"""Bounded official Telegram Bot API transport; no browser sessions or SDK loop.

Telegram requires the bot token in the URL path. urllib does not log requests;
we refuse redirects/proxies and never include raw URL/errors/response text in
exceptions. There is no automatic network retry, especially for sendMessage.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from ..google_calendar import SecretToolStore
from . import ChannelError

TOKEN = re.compile(r'[0-9]{5,20}:[A-Za-z0-9_-]{20,100}\Z')


class ChannelSecrets(SecretToolStore):
    service = 'hutch.channels'
    feature_name = 'channel'
    account_pattern = re.compile(r'ch_[0-9a-f]{24}\Z')
    probe_account = 'ch_000000000000000000000000'

    def put(self, account_id, value):
        self._call(['store','--label=Hutch Telegram bot token','service',self.service,
                    'account',self._account(account_id)],input_text=value+'\n')


class TelegramFailure(ChannelError):
    def __init__(self, *, uncertain=False, retry_after=0, status=0):
        self.uncertain = uncertain
        self.retry_after = retry_after
        self.status = status
        super().__init__('Telegram delivery could not be confirmed.' if uncertain else
                         'Telegram rate limit; retry scheduled.' if retry_after else
                         'Telegram rejected the request. Check the bot token and connection.')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Telegram:
    def __init__(self, token, *, opener=None):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise ChannelError('Enter a valid Telegram bot token from BotFather.')
        self._token = token
        self._opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def call(self, method, payload):
        if method not in ('getMe','getUpdates','sendMessage'):
            raise ChannelError('Unsupported Telegram operation.')
        sending = method == 'sendMessage'
        request = urllib.request.Request('https://api.telegram.org/bot'+self._token+'/'+method,
            data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'}, method='POST')
        try:
            try:
                response = self._opener.open(request, timeout=15)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status = response.code
                raw = response.read(1_048_577)
            if len(raw)>1_048_576:
                raise TelegramFailure(uncertain=sending, status=status)
            data = json.loads(raw)
            if not isinstance(data,dict):
                raise TelegramFailure(uncertain=sending, status=status)
            if status == 429 or data.get('error_code') == 429:
                delay = data.get('parameters',{}).get('retry_after')
                delay = max(1,min(delay,3600)) if type(delay) is int else 60
                raise TelegramFailure(retry_after=delay,status=429)
            if not 200<=status<300 or data.get('ok') is not True:
                code = data.get('error_code')
                definite_rejection = 400<=status<500 or (200<=status<300 and type(code) is int and 400<=code<500)
                raise TelegramFailure(uncertain=sending and not definite_rejection,status=status)
            result = data.get('result')
            if method == 'getMe' and (not isinstance(result,dict) or result.get('is_bot') is not True
                                      or type(result.get('id')) is not int or result['id']<=0):
                raise TelegramFailure()
            if method == 'getUpdates' and (not isinstance(result,list) or len(result)>50
                                          or any(not isinstance(row,dict) for row in result)):
                raise TelegramFailure()
            if sending and (not isinstance(result,dict) or type(result.get('message_id')) is not int or result['message_id']<=0
                            or result.get('chat',{}).get('id') != int(payload['chat_id'])):
                raise TelegramFailure(uncertain=True)
            return result
        except TelegramFailure:
            raise
        except Exception:
            raise TelegramFailure(uncertain=sending) from None

    def updates(self, cursor):
        return self.call('getUpdates', {'offset':cursor,'timeout':0,'limit':50,'allowed_updates':['message']})

    def send(self, sender, text):
        return str(self.call('sendMessage',{'chat_id':sender,'text':text,
            'link_preview_options':{'is_disabled':True},'protect_content':True})['message_id'])
