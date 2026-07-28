import datetime
import logging

from django.conf import settings
from django.db import transaction

from vehicle_fleet.constants import MACROSCOP_DIRECTION_MAP, GatePassSource
from vehicle_fleet.models import GateCamera, MacroscopIntegrationState, VehicleGatePass
from vehicle_fleet.services import FleetVehicleService, PlateNormalizer

logger = logging.getLogger(__name__)


def _resolve_direction(parsed_event, gate_camera):
    mapped = MACROSCOP_DIRECTION_MAP.get(parsed_event.direction)
    if mapped:
        return mapped
    if gate_camera:
        return gate_camera.role
    return None


def process_plate_event(parsed_event, *, terminal, min_reliability=None, dedup_window_sec=None, source=None):
    """Алгоритм обработки события "Обнаружен автономер" (см. план T-068).

    Возвращает созданный VehicleGatePass, либо None, если событие отброшено
    (низкая достоверность, дубликат по EventId, дубликат в окне дедупликации,
    не удалось определить направление).
    """
    if source is None:
        source = GatePassSource.MACROSCOP
    config = settings.MACROSCOP_INTEGRATION
    if min_reliability is None:
        min_reliability = config['MIN_RELIABILITY']
    if dedup_window_sec is None:
        dedup_window_sec = config['DEDUP_WINDOW_SEC']

    if parsed_event.reliability is not None and parsed_event.reliability < min_reliability:
        logger.debug(
            'Событие %s отброшено: reliability %.4f < %.4f',
            parsed_event.event_id, parsed_event.reliability, min_reliability,
        )
        return None

    if source != GatePassSource.MACROSCOP and VehicleGatePass.objects.filter(macroscop_event_id=parsed_event.event_id).exists():
        logger.warning('Дубликат события %s: %s', source, parsed_event.event_id)
        return None

    registration_number = PlateNormalizer.normalize(parsed_event.numberplate)

    gate_camera = GateCamera.objects.filter(
        terminal=terminal, macroscop_channel_id=parsed_event.channel_id,
    ).first()
    if gate_camera is None:
        logger.warning(
            'Камера Macroscop %s не привязана к терминалу %s (событие %s)',
            parsed_event.channel_id, terminal.pk, parsed_event.event_id,
        )

    direction = _resolve_direction(parsed_event, gate_camera)
    if direction is None:
        logger.warning(
            'Не удалось определить направление для события %s (канал %s)',
            parsed_event.event_id, parsed_event.channel_id,
        )
        return None

    window_start = parsed_event.passed_at - datetime.timedelta(seconds=dedup_window_sec)
    duplicate_in_window = VehicleGatePass.objects.filter(
        terminal=terminal,
        registration_number=registration_number,
        direction=direction,
        gate_camera=gate_camera,
        passed_at__gte=window_start,
        passed_at__lte=parsed_event.passed_at,
    ).exists()
    if duplicate_in_window:
        logger.info(
            'Событие %s пропущено: похожая запись уже есть в окне дедупликации (%ss)',
            parsed_event.event_id, dedup_window_sec,
        )
        return None

    fleet_vehicle = FleetVehicleService.find_for_terminal(terminal, registration_number)

    with transaction.atomic():
        gate_pass = VehicleGatePass.objects.create(
            terminal=terminal,
            fleet_vehicle=fleet_vehicle,
            gate_camera=gate_camera,
            registration_number=registration_number,
            direction=direction,
            passed_at=parsed_event.passed_at,
            source=source,
            reliability=parsed_event.reliability,
            recognized_brand=parsed_event.recognized_brand,
            recognized_color=parsed_event.recognized_color,
            recognized_type=parsed_event.recognized_type,
            macroscop_event_id=parsed_event.event_id if source != GatePassSource.MACROSCOP else None,
            raw_event=parsed_event.raw,
        )
        MacroscopIntegrationState.objects.update_or_create(
            terminal=terminal,
            defaults={'last_event_at': parsed_event.passed_at, 'is_connected': True},
        )

    return gate_pass
