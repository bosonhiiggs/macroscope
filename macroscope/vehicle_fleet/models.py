from django.conf import settings
from django.db import models

from vehicle_fleet.constants import GateCameraRole, GatePassDirection, GatePassSource


class TimeStampedModel(models.Model):
    """Локальный аналог TimeStampVisibleModel из Steiza."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class FleetVehicle(TimeStampedModel):
    """Машина автопарка терминала.

    Логика: справочник «своих» машин; при совпадении номера в событии
    Macroscop запись журнала ссылается на эту сущность.
    """

    terminal = models.ForeignKey(
        'terminal.Terminal', on_delete=models.CASCADE, related_name='fleet_vehicles',
    )
    registration_number = models.CharField(max_length=32)
    brand = models.CharField(max_length=128, blank=True, default='')
    model = models.CharField(max_length=128, blank=True, default='')
    comment = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('terminal', 'registration_number')]

    def __str__(self):
        return self.registration_number


class GateCamera(TimeStampedModel):
    """Привязка канала Macroscop к терминалу.

    Логика: ChannelId из Macroscop -> роль (въезд/выезд) для определения
    direction, если поле direction в событии отсутствует или неоднозначно.
    """

    terminal = models.ForeignKey(
        'terminal.Terminal', on_delete=models.CASCADE, related_name='gate_cameras',
    )
    macroscop_channel_id = models.UUIDField()
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=16, choices=GateCameraRole.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('terminal', 'macroscop_channel_id')]

    def __str__(self):
        return self.name


class VehicleGatePass(TimeStampedModel):
    """Запись журнала въезда/выезда.

    Логика: одна строка = один факт проезда через КПП.
    """

    terminal = models.ForeignKey(
        'terminal.Terminal', on_delete=models.CASCADE, related_name='vehicle_gate_passes',
    )
    fleet_vehicle = models.ForeignKey(
        FleetVehicle, null=True, blank=True, on_delete=models.SET_NULL, related_name='gate_passes',
    )
    gate_camera = models.ForeignKey(
        GateCamera, null=True, blank=True, on_delete=models.SET_NULL, related_name='gate_passes',
    )
    registration_number = models.CharField(max_length=32)
    direction = models.CharField(max_length=16, choices=GatePassDirection.choices)
    passed_at = models.DateTimeField()
    source = models.CharField(max_length=16, choices=GatePassSource.choices)
    reliability = models.FloatField(null=True, blank=True)
    recognized_brand = models.CharField(max_length=128, blank=True, default='')
    recognized_color = models.CharField(max_length=64, blank=True, default='')
    recognized_type = models.CharField(max_length=64, blank=True, default='')
    macroscop_event_id = models.UUIDField(null=True, blank=True, unique=True)
    raw_event = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ['-passed_at']

    def __str__(self):
        return f'{self.registration_number} ({self.direction}) {self.passed_at}'


class MacroscopIntegrationState(models.Model):
    """Singleton на терминал: курсор интеграции, статус подключения."""

    terminal = models.OneToOneField(
        'terminal.Terminal', on_delete=models.CASCADE, related_name='macroscop_state',
    )
    last_event_at = models.DateTimeField(null=True, blank=True)
    last_archive_poll_at = models.DateTimeField(null=True, blank=True)
    is_connected = models.BooleanField(default=False)
    last_error = models.TextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'MacroscopIntegrationState({self.terminal_id})'
