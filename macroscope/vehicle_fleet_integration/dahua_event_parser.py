import datetime
import logging
import uuid
from datetime import timezone as dt_timezone

from vehicle_fleet_integration.event_parser import ParsedPlateEvent

logger = logging.getLogger(__name__)

# DrivingDirection[0] из реального события Dahua ITC413
_DAHUA_DIRECTION_MAP = {
    'Approach': 'entry',
    'Enter':    'entry',
    'In':       'entry',
    'Leave':    'exit',
    'Exit':     'exit',
    'Out':      'exit',
}


def parse_dahua_body(body):
    """Разбирает тело multipart-части: 'Code=X;action=Y;index=Z;data={...JSON...}'.

    Возвращает (code, action, data_dict) или None.
    """
    import json

    data_idx = body.find(';data=')
    if data_idx == -1:
        return None

    header = body[:data_idx]
    data_raw = body[data_idx + len(';data='):]

    params = {}
    for part in header.split(';'):
        if '=' in part:
            k, v = part.split('=', 1)
            params[k.strip()] = v.strip()

    try:
        data = json.loads(data_raw)
    except (ValueError, TypeError):
        logger.warning('Не удалось распарсить data Dahua: %r', data_raw[:200])
        return None

    return params.get('Code', ''), params.get('action', ''), data


def extract_plate_event_dahua(body):
    """Возвращает ParsedPlateEvent из события Dahua TrafficJunction, либо None.

    Поля основаны на реальном JSON от Dahua DHI-ITC413-PW4D-IZ3:
      - PlateNumber  → data['TrafficCar']['PlateNumber']
      - Direction    → data['TrafficCar']['DrivingDirection'][0]  ('Leave'/'Approach')
      - UTC          → data['UTC']  (Unix timestamp, целое число)
      - Confidence   → data['Object']['Confidence']  (0–100)
      - EventID      → data['EventID']  (целое число → конвертируем в UUID)
    """
    parsed = parse_dahua_body(body)
    if parsed is None:
        return None

    code, action, data = parsed

    if code not in ('TrafficJunction', 'PlateDetect'):
        return None

    # action='Pulse' — нормальный режим для ITC413
    if action not in ('Start', 'Pulse', ''):
        logger.debug('Событие Dahua %s action=%s пропущено', code, action)
        return None

    traffic_car = data.get('TrafficCar') or {}

    # Номерной знак
    numberplate = (
        traffic_car.get('PlateNumber')
        or (data.get('Object') or {}).get('Text')
    )
    if not numberplate:
        logger.debug('Событие Dahua без номера: TrafficCar=%s', traffic_car)
        return None

    # Время события. Dahua называет поле 'UTC', но там московское время.
    # Реальный UTC лежит в 'RealUTC'. Fallback на 'UTC' если RealUTC отсутствует.
    utc_ts = data.get('RealUTC') or traffic_car.get('RealUTC') or data.get('UTC') or traffic_car.get('UTC')
    if not utc_ts:
        logger.warning('Событие Dahua без временной метки: %s', data.get('EventID'))
        return None
    passed_at = datetime.datetime.fromtimestamp(int(utc_ts), tz=dt_timezone.utc)

    # Направление
    driving_dir = traffic_car.get('DrivingDirection') or []
    direction_raw = driving_dir[0] if driving_dir else ''
    direction = _DAHUA_DIRECTION_MAP.get(direction_raw)
    if not direction:
        logger.debug('Неизвестное направление Dahua: %r', direction_raw)

    # Достоверность: 0–100 → 0.0–1.0
    obj = data.get('Object') or {}
    confidence_raw = obj.get('Confidence')
    reliability = float(confidence_raw) / 100.0 if confidence_raw is not None else None

    # EventID (целое) → UUID для хранения в macroscop_event_id (UUIDField)
    event_id_int = data.get('EventID')
    event_id = str(uuid.UUID(int=int(event_id_int))) if event_id_int is not None else None

    return ParsedPlateEvent(
        event_id=event_id,
        channel_id=None,
        numberplate=numberplate,
        passed_at=passed_at,
        direction=direction,
        reliability=reliability,
        recognized_brand='',
        recognized_color=traffic_car.get('VehicleColor') or '',
        recognized_type=traffic_car.get('CarType') or '',
        raw=data,
    )