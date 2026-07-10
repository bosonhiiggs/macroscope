import base64
import logging

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class MacroscopHttpClient:
    """HTTP-клиент Macroscop: Basic auth (REST API) / query auth (HTTP API), retry, таймауты."""

    def __init__(self, base_url, login, password_md5, timeout=30, max_retries=2):
        self.base_url = base_url.rstrip('/')
        self.login = login
        self.password_md5 = password_md5
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(total=max_retries, backoff_factor=1, status_forcelist=(500, 502, 503, 504))
        self.session.mount('http://', HTTPAdapter(max_retries=retry))
        self.session.mount('https://', HTTPAdapter(max_retries=retry))

    @classmethod
    def from_settings(cls):
        config = settings.MACROSCOP_INTEGRATION
        return cls(
            base_url=config['BASE_URL'],
            login=config['LOGIN'],
            password_md5=config['PASSWORD_MD5'],
            timeout=config['REQUEST_TIMEOUT_SEC'],
        )

    @property
    def _basic_auth_header(self):
        token = base64.b64encode(f'{self.login}:{self.password_md5}'.encode()).decode()
        return {'Authorization': f'Basic {token}'}

    @property
    def _query_auth_params(self):
        return {'login': self.login, 'password': self.password_md5}

    def get_channels(self):
        logger.debug('Запрос списка камер Macroscop: %s/api/channels', self.base_url)
        response = self.session.get(
            f'{self.base_url}/api/channels', headers=self._basic_auth_header, timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_archive_event_types(self):
        params = {**self._query_auth_params, 'responsetype': 'json'}
        response = self.session.get(
            f'{self.base_url}/archive_event_types', params=params, timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_archive_events(self, start_time_utc, end_time_utc, event_ids, channel_ids, search_limit_count=1000):
        payload = {
            'startTimeUtc': start_time_utc,
            'endTimeUtc': end_time_utc,
            'eventIds': event_ids,
            'channelIds': channel_ids,
            'searchLimitCount': search_limit_count,
        }
        logger.debug('Опрос архива событий Macroscop: %s -> %s', start_time_utc, end_time_utc)
        response = self.session.post(
            f'{self.base_url}/archive_events',
            params=self._query_auth_params,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def stream_events(self, channel_id=None, event_filter=None, mode=None):
        """Долгоживущее соединение к /event. Возвращает итератор JSON-строк (по одной на объект).

        Macroscop отдаёт pretty-printed JSON (несколько строк на объект), поэтому строки
        накапливаются в буфер и yield-ятся целым объектом при получении закрывающей '}'.

        Переподключение при обрыве — ответственность вызывающего кода (stream_worker),
        здесь только однократное открытие потока.
        """
        params = {**self._query_auth_params, 'responsetype': 'json'}
        if channel_id:
            params['channelid'] = channel_id
        if event_filter:
            params['filter'] = event_filter
        if mode:
            params['mode'] = mode

        response = requests.get(
            f'{self.base_url}/event', params=params, stream=True, timeout=self.timeout,
        )
        response.raise_for_status()
        buffer = []
        for line in response.iter_lines(decode_unicode=True):
            if line is None:
                continue
            stripped = line.lstrip('﻿').strip()
            if not stripped:
                continue
            buffer.append(stripped)
            if stripped == '}':
                yield '\n'.join(buffer)
                buffer = []
        if buffer:
            yield '\n'.join(buffer)
