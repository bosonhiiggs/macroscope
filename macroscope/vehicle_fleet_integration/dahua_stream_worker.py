import logging
import time

import requests

from vehicle_fleet_integration.dahua_client import DahuaHttpClient
from vehicle_fleet_integration.dahua_event_parser import extract_plate_event_dahua
from vehicle_fleet.constants import GatePassSource
from vehicle_fleet_integration.event_processor import process_plate_event

logger = logging.getLogger(__name__)

MAX_BACKOFF_SEC = 60


def run_dahua_stream_worker(terminal, *, gate_camera=None, client=None, stop_event=None):
    """Долгоживущий цикл чтения Dahua eventManager.cgi с переподключением (backoff 1s → 60s).

    gate_camera — объект GateCamera для этой камеры; используется как fallback-направление
    и подставляется в ParsedPlateEvent.channel_id (камера одна, channel зафиксирован).
    """
    from django.conf import settings as django_settings
    client = client or DahuaHttpClient.from_settings()
    min_reliability = django_settings.DAHUA_INTEGRATION.get('MIN_RELIABILITY', 0.60)
    backoff = 1

    while stop_event is None or not stop_event.is_set():
        try:
            logger.info(
                'Подключение к потоку событий Dahua (терминал %s)',
                terminal.pk,
            )
            for body in client.stream_events():
                backoff = 1
                logger.info('Dahua событие:\n%s', body)
                parsed_event = extract_plate_event_dahua(body)
                if parsed_event is None:
                    continue

                # Подставляем channel_id из GateCamera, если передана
                if gate_camera is not None and parsed_event.channel_id is None:
                    parsed_event.channel_id = str(gate_camera.macroscop_channel_id)

                result = process_plate_event(
                    parsed_event, terminal=terminal, min_reliability=min_reliability,
                    source=GatePassSource.DAHUA,
                )
                if result is not None:
                    logger.info(
                        'Создан VehicleGatePass #%s (%s, %s) из события Dahua',
                        result.pk, result.registration_number, result.direction,
                    )

        except requests.RequestException as exc:
            logger.warning(
                'Поток событий Dahua прервался: %s. Реконнект через %ss',
                exc, backoff,
            )
        except Exception as exc:
            logger.exception(
                'Неожиданная ошибка в Dahua-воркере: %s. Реконнект через %ss',
                exc, backoff,
            )

        if stop_event is not None and stop_event.is_set():
            break

        if stop_event is not None:
            stop_event.wait(timeout=backoff)
        else:
            time.sleep(backoff)

        backoff = min(backoff * 2, MAX_BACKOFF_SEC)