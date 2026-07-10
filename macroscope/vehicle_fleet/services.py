import re

from rest_framework import serializers

from vehicle_fleet.constants import GatePassSource
from vehicle_fleet.models import FleetVehicle, VehicleGatePass


class PlateNormalizer:
    """Нормализация госномера: upper case, без пробелов/дефисов, кириллица сохраняется."""

    _STRIP_RE = re.compile(r'[\s\-]+')

    @classmethod
    def normalize(cls, raw):
        if not raw:
            return ''
        return cls._STRIP_RE.sub('', raw).upper()


class FleetVehicleService:
    @staticmethod
    def validate_unique(terminal, registration_number, exclude_id=None):
        qs = FleetVehicle.objects.filter(terminal=terminal, registration_number=registration_number)
        if exclude_id:
            qs = qs.exclude(pk=exclude_id)
        if qs.exists():
            raise serializers.ValidationError(
                {'registration_number': 'Машина с таким номером уже есть в автопарке терминала.'}
            )

    @staticmethod
    def find_for_terminal(terminal, registration_number):
        return FleetVehicle.objects.filter(
            terminal=terminal, registration_number=registration_number,
        ).first()


class GatePassService:
    @staticmethod
    def create_manual(terminal, user, *, registration_number, direction, passed_at, fleet_vehicle=None):
        normalized = PlateNormalizer.normalize(registration_number)
        return VehicleGatePass.objects.create(
            terminal=terminal,
            fleet_vehicle=fleet_vehicle or FleetVehicleService.find_for_terminal(terminal, normalized),
            registration_number=normalized,
            direction=direction,
            passed_at=passed_at,
            source=GatePassSource.MANUAL,
            created_by=user,
        )
