from django.test import TestCase
from rest_framework.exceptions import ValidationError

from terminal.models import Terminal
from vehicle_fleet.models import FleetVehicle
from vehicle_fleet.services import FleetVehicleService, PlateNormalizer


class PlateNormalizerTests(TestCase):
    def test_strips_spaces_and_hyphens_and_upper_cases(self):
        self.assertEqual(PlateNormalizer.normalize('a 123 bc-77'), 'A123BC77')

    def test_keeps_cyrillic(self):
        self.assertEqual(PlateNormalizer.normalize('а123вс77'), 'А123ВС77')

    def test_empty_input(self):
        self.assertEqual(PlateNormalizer.normalize(''), '')
        self.assertEqual(PlateNormalizer.normalize(None), '')


class FleetVehicleServiceTests(TestCase):
    def setUp(self):
        self.terminal = Terminal.objects.create(name='Терминал 1', slug='term-1')

    def test_validate_unique_passes_when_no_duplicate(self):
        FleetVehicleService.validate_unique(self.terminal, 'A123BC77')

    def test_validate_unique_raises_on_duplicate(self):
        FleetVehicle.objects.create(terminal=self.terminal, registration_number='A123BC77')
        with self.assertRaises(ValidationError):
            FleetVehicleService.validate_unique(self.terminal, 'A123BC77')

    def test_validate_unique_excludes_self_on_update(self):
        vehicle = FleetVehicle.objects.create(terminal=self.terminal, registration_number='A123BC77')
        FleetVehicleService.validate_unique(self.terminal, 'A123BC77', exclude_id=vehicle.id)

    def test_find_for_terminal_returns_none_when_missing(self):
        self.assertIsNone(FleetVehicleService.find_for_terminal(self.terminal, 'A123BC77'))
