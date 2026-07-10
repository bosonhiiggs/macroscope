import json
import os
import uuid

from django.test import TestCase

from terminal.models import Terminal
from vehicle_fleet.constants import GateCameraRole, GatePassDirection, GatePassSource
from vehicle_fleet.models import FleetVehicle, GateCamera, MacroscopIntegrationState, VehicleGatePass
from vehicle_fleet_integration.event_parser import extract_plate_event
from vehicle_fleet_integration.event_processor import process_plate_event

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'plate_event.json')


def load_fixture():
    with open(FIXTURE_PATH, encoding='utf-8') as fh:
        return json.load(fh)


class ProcessPlateEventTests(TestCase):
    def setUp(self):
        self.terminal = Terminal.objects.create(name='Терминал 1', slug='term-1')
        self.channel_id = '7d53f293-70d9-45df-9243-afe5fac19c65'
        self.gate_camera = GateCamera.objects.create(
            terminal=self.terminal, macroscop_channel_id=self.channel_id,
            name='КПП Въезд', role=GateCameraRole.ENTRY,
        )

    def _parsed(self, overrides=None, remove_keys=None):
        data = dict(load_fixture())
        for key in remove_keys or ():
            data.pop(key, None)
        data.update(overrides or {})
        return extract_plate_event(data)

    def test_creates_gate_pass_and_links_known_vehicle(self):
        FleetVehicle.objects.create(terminal=self.terminal, registration_number='A123BC77')
        gate_pass = process_plate_event(self._parsed(), terminal=self.terminal)
        self.assertIsNotNone(gate_pass)
        self.assertEqual(gate_pass.direction, GatePassDirection.ENTRY)
        self.assertEqual(gate_pass.source, GatePassSource.MACROSCOP)
        self.assertIsNotNone(gate_pass.fleet_vehicle)
        self.assertEqual(gate_pass.gate_camera, self.gate_camera)
        state = MacroscopIntegrationState.objects.get(terminal=self.terminal)
        self.assertTrue(state.is_connected)
        self.assertIsNotNone(state.last_event_at)

    def test_creates_gate_pass_for_unknown_vehicle(self):
        gate_pass = process_plate_event(self._parsed(), terminal=self.terminal)
        self.assertIsNotNone(gate_pass)
        self.assertIsNone(gate_pass.fleet_vehicle)

    def test_duplicate_event_id_is_skipped(self):
        first = process_plate_event(self._parsed(), terminal=self.terminal)
        self.assertIsNotNone(first)
        second = process_plate_event(self._parsed(), terminal=self.terminal)
        self.assertIsNone(second)
        self.assertEqual(VehicleGatePass.objects.count(), 1)

    def test_low_reliability_is_dropped(self):
        parsed = self._parsed(overrides={'Reliability': '0,3'})
        gate_pass = process_plate_event(parsed, terminal=self.terminal, min_reliability=0.85)
        self.assertIsNone(gate_pass)
        self.assertEqual(VehicleGatePass.objects.count(), 0)

    def test_direction_falls_back_to_camera_role_when_missing(self):
        parsed = self._parsed(overrides={'EventId': str(uuid.uuid4())}, remove_keys=['direction'])
        gate_pass = process_plate_event(parsed, terminal=self.terminal)
        self.assertIsNotNone(gate_pass)
        self.assertEqual(gate_pass.direction, GatePassDirection.ENTRY)

    def test_event_without_direction_and_unbound_camera_is_dropped(self):
        parsed = self._parsed(
            overrides={'EventId': str(uuid.uuid4()), 'ChannelId': str(uuid.uuid4())},
            remove_keys=['direction'],
        )
        gate_pass = process_plate_event(parsed, terminal=self.terminal)
        self.assertIsNone(gate_pass)

    def test_unbound_camera_with_known_direction_still_creates_pass(self):
        parsed = self._parsed(overrides={'EventId': str(uuid.uuid4()), 'ChannelId': str(uuid.uuid4())})
        gate_pass = process_plate_event(parsed, terminal=self.terminal)
        self.assertIsNotNone(gate_pass)
        self.assertIsNone(gate_pass.gate_camera)

    def test_dedup_window_skips_repeated_plate(self):
        process_plate_event(self._parsed(), terminal=self.terminal)
        duplicate = self._parsed(overrides={'EventId': str(uuid.uuid4())})
        gate_pass = process_plate_event(duplicate, terminal=self.terminal, dedup_window_sec=60)
        self.assertIsNone(gate_pass)
        self.assertEqual(VehicleGatePass.objects.count(), 1)
