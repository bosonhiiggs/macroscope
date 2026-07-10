import logging

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from requests.auth import HTTPDigestAuth
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_BOUNDARY = b'--myboundary'


class DahuaHttpClient:
    """HTTP-клиент для Dahua ITC-камеры: Digest-аутентификация, multipart/x-mixed-replace поток событий."""

    def __init__(self, base_url, login, password, timeout=30, max_retries=2):
        self.base_url = base_url.rstrip('/')
        self.auth = HTTPDigestAuth(login, password)
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(total=max_retries, backoff_factor=1, status_forcelist=(500, 502, 503, 504))
        self.session.mount('http://', HTTPAdapter(max_retries=retry))
        self.session.mount('https://', HTTPAdapter(max_retries=retry))

    @classmethod
    def from_settings(cls):
        config = settings.DAHUA_INTEGRATION
        return cls(
            base_url=config['BASE_URL'],
            login=config['LOGIN'],
            password=config['PASSWORD'],
            timeout=config['REQUEST_TIMEOUT_SEC'],
        )

    def stream_events(self, codes=None, heartbeat=5):
        """Долгоживущее соединение к eventManager.cgi.

        Возвращает итератор строк тела каждой multipart-части (кроме heartbeat).
        Формат части: 'Code=TrafficJunction;action=Start;index=0;data={...}'
        """
        params = {
            'action': 'attach',
            'codes': f'[{",".join(codes or ["TrafficJunction", "PlateDetect"])}]',
            'heartbeat': heartbeat,
        }
        url = f'{self.base_url}/cgi-bin/eventManager.cgi'
        logger.debug('Подключение к потоку событий Dahua: %s params=%s', url, params)

        response = self.session.get(url, auth=self.auth, params=params, stream=True, timeout=self.timeout)
        response.raise_for_status()

        yield from _iter_multipart_bodies(response)


def _iter_multipart_bodies(response):
    """Разбирает multipart/x-mixed-replace поток, yield-ит тело каждой части."""
    in_headers = False
    in_body = False
    body_lines = []

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode('utf-8', errors='replace')

        # Детектируем граничный маркер (может прийти с суффиксом -- при закрытии)
        if raw_line.strip().startswith('--myboundary'):
            if body_lines:
                body = '\n'.join(body_lines).strip()
                if body and not _is_heartbeat(body):
                    yield body
                body_lines = []
            in_headers = True
            in_body = False
            continue

        if in_headers:
            if raw_line.strip() == '':
                # Пустая строка = конец заголовков, начало тела
                in_headers = False
                in_body = True
            # Заголовки (Content-Type, Content-Length) нас не интересуют — пропускаем
            continue

        if in_body:
            body_lines.append(raw_line)

    # Последняя незавершённая часть (если сервер закрыл соединение без маркера)
    if body_lines:
        body = '\n'.join(body_lines).strip()
        if body and not _is_heartbeat(body):
            yield body


def _is_heartbeat(body):
    """Отфильтровывает heartbeat-ы и части с просочившимися заголовками."""
    stripped = body.strip()
    return (
        stripped == 'Heartbeat'
        or stripped.startswith('Content-Type:')
        or stripped.startswith('Content-Length:')
        or 'Heartbeat' in stripped and len(stripped) < 200
    )