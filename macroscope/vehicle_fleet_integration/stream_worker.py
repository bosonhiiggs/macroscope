import logging
import time

import requests

from vehicle_fleet_integration.client import MacroscopHttpClient
from vehicle_fleet_integration.event_parser import extract_plate_event, parse_event_line
from vehicle_fleet_integration.event_processor import process_plate_event

logger = logging.getLogger(__name__)

MAX_BACKOFF_SEC = 60


def run_stream_worker(terminal, *, channel_id=None, event_filter=None, mode=None, client=None, stop_event=None):
    """Долгоживущий цикл чтения /event с переподключением (backoff 1s -> 2s -> ... -> 60s).

    stop_event (threading.Event) позволяет остановить цикл снаружи; без него цикл бесконечен.
    """
    client = client or MacroscopHttpClient.from_settings()
    backoff = 1

    while stop_event is None or not stop_event.is_set():
        try:
            logger.info('Подключение к потоку событий Macroscop (терминал %s)', terminal.pk)
            for line in client.stream_events(channel_id=channel_id, event_filter=event_filter, mode=mode):
                backoff = 1
                data = parse_event_line(line)
                if data is None:
                    continue
                parsed_event = extract_plate_event(data)
                if parsed_event is None:
                    continue
                process_plate_event(parsed_event, terminal=terminal)
        except requests.RequestException as exc:
            logger.warning('Поток событий Macroscop прервался: %s. Реконнект через %ss', exc, backoff)

        if stop_event is not None and stop_event.is_set():
            break
        time.sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF_SEC)
