import datetime
import json
import logging
from zoneinfo import ZoneInfo

from django.conf import settings

from vehicle_fleet.constants import MACROSCOP_PLATE_EVENT_DESCRIPTION

logger = logging.getLogger(__name__)

_ZONED_TIMESTAMP_FORMATS = ('%d.%m.%Y %H:%M:%S.%f %z', '%d.%m.%Y %H:%M:%S %z')
_NAIVE_TIMESTAMP_FORMATS = ('%d.%m.%Y %H:%M:%S.%f', '%d.%m.%Y %H:%M:%S')


class ParsedPlateEvent:
    __slots__ = (
        'event_id', 'channel_id', 'numberplate', 'passed_at', 'direction',
        'reliability', 'recognized_brand', 'recognized_color', 'recognized_type', 'raw',
    )

    def __init__(self, **kwargs):
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


def parse_event_line(line):
    """Парсит одну NDJSON-строку. Возвращает dict, либо None для KeepAlive/мусора."""
    try:
        data = json.loads(line)
    except (TypeError, ValueError):
        logger.warning('Не удалось распарсить строку события Macroscop: %r', line)
        return None

    if data.get('InitiatorName') == 'System':
        return None  # KeepAlive

    return data


def _parse_timestamp(value):
    """Парсит ZonedTimestamp (с offset) или bare Timestamp (без offset).

    Timestamp без offset считается локальным временем терминала
    (MACROSCOP_INTEGRATION['TERMINAL_TIMEZONE'], по умолчанию Europe/Moscow).
    """
    for fmt in _ZONED_TIMESTAMP_FORMATS:
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue

    for fmt in _NAIVE_TIMESTAMP_FORMATS:
        try:
            naive = datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
        terminal_tz = ZoneInfo(settings.MACROSCOP_INTEGRATION['TERMINAL_TIMEZONE'])
        return naive.replace(tzinfo=terminal_tz)

    return None


def _parse_reliability(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(',', '.'))
    except ValueError:
        return None


def extract_plate_event(data):
    """Возвращает ParsedPlateEvent для события "Обнаружен автономер", либо None."""
    if not data or data.get('EventDescription') != MACROSCOP_PLATE_EVENT_DESCRIPTION:
        return None

    event_id = data.get('EventId')
    channel_id = data.get('ChannelId')
    numberplate = data.get('Numberplate') or data.get('plateText')
    timestamp_raw = data.get('ZonedTimestamp') or data.get('Timestamp')

    if not (event_id and channel_id and numberplate and timestamp_raw):
        logger.warning('Событие "Обнаружен автономер" без обязательных полей: %s', data)
        return None

    passed_at = _parse_timestamp(timestamp_raw)
    if passed_at is None:
        logger.warning('Не удалось распарсить ZonedTimestamp/Timestamp: %r', timestamp_raw)
        return None

    return ParsedPlateEvent(
        event_id=event_id,
        channel_id=channel_id,
        numberplate=numberplate,
        passed_at=passed_at,
        direction=data.get('direction'),
        reliability=_parse_reliability(data.get('Reliability')),
        recognized_brand=data.get('RecognizedCarBrand', ''),
        recognized_color=data.get('RecognizedCarColors', ''),
        recognized_type=data.get('RecognizedCarType', ''),
        raw=data,
    )
