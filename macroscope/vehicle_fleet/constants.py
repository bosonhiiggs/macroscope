from django.db import models


class GateCameraRole(models.TextChoices):
    ENTRY = 'entry', 'Въезд'
    EXIT = 'exit', 'Выезд'


class GatePassDirection(models.TextChoices):
    ENTRY = 'entry', 'Въезд'
    EXIT = 'exit', 'Выезд'


class GatePassSource(models.TextChoices):
    MACROSCOP = 'macroscop', 'Macroscop'
    MANUAL = 'manual', 'Вручную'


# Macroscop отдаёт direction как русскую строку в событии — маппинг на наш choice.
MACROSCOP_DIRECTION_MAP = {
    'Въезд': GatePassDirection.ENTRY,
    'Выезд': GatePassDirection.EXIT,
    # Dahua-воркер уже маппит DrivingDirection на наши значения до попадания сюда
    'entry': GatePassDirection.ENTRY,
    'exit': GatePassDirection.EXIT,
}

MACROSCOP_PLATE_EVENT_DESCRIPTION = 'Обнаружен автономер'
