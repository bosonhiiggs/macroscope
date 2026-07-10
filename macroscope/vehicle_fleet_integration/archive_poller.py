import datetime
import logging

from django.utils import timezone

from vehicle_fleet.models import MacroscopIntegrationState
from vehicle_fleet_integration.client import MacroscopHttpClient
from vehicle_fleet_integration.event_parser import extract_plate_event
from vehicle_fleet_integration.event_processor import process_plate_event

logger = logging.getLogger(__name__)

_MACROSCOP_DATETIME_FORMAT = '%d.%m.%Y %H:%M:%S.%f'
_DEFAULT_BACKFILL = datetime.timedelta(hours=24)


def run_archive_poll(terminal, *, event_type_id, channel_ids=None, client=None, now=None):
    """Fallback-опрос /archive_events за интервал [курсор, now].

    Используется для первичного backfill и восстановления после простоя сервиса.
    """
    client = client or MacroscopHttpClient.from_settings()
    now = now or timezone.now()

    state, _ = MacroscopIntegrationState.objects.get_or_create(terminal=terminal)
    start = state.last_event_at or (now - _DEFAULT_BACKFILL)

    raw_response = client.get_archive_events(
        start_time_utc=start.strftime(_MACROSCOP_DATETIME_FORMAT)[:-3],
        end_time_utc=now.strftime(_MACROSCOP_DATETIME_FORMAT)[:-3],
        event_ids=[event_type_id],
        channel_ids=channel_ids or [],
    )
    # Точная форма ответа /archive_events не зафиксирована в спеке T-068 — уточнить на реальном сервере.
    events = raw_response.get('events', []) if isinstance(raw_response, dict) else raw_response

    created = 0
    for data in events:
        parsed_event = extract_plate_event(data)
        if parsed_event is None:
            continue
        if process_plate_event(parsed_event, terminal=terminal) is not None:
            created += 1

    state.last_archive_poll_at = now
    state.save(update_fields=['last_archive_poll_at'])
    logger.info(
        'Архивный опрос терминала %s за [%s, %s]: создано %s записей',
        terminal.pk, start, now, created,
    )
    return created
