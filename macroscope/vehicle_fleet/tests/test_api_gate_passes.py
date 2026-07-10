from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from terminal.models import Terminal
from vehicle_fleet.constants import GatePassDirection, GatePassSource
from vehicle_fleet.models import FleetVehicle, VehicleGatePass


class VehicleGatePassApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='dispatcher', password='pass12345')
        self.client.force_authenticate(self.user)
        self.terminal = Terminal.objects.create(name='Терминал 1', slug='term-1')
        self.list_url = f'/api/terminals/{self.terminal.pk}/vehicle-gate-passes/'

    def test_manual_create_links_existing_fleet_vehicle(self):
        FleetVehicle.objects.create(terminal=self.terminal, registration_number='A123BC77')
        response = self.client.post(
            self.list_url,
            {
                'registration_number': 'a123bc77',
                'direction': GatePassDirection.ENTRY,
                'passed_at': '2026-06-24T08:15:22+03:00',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['source'], GatePassSource.MANUAL)
        self.assertIsNotNone(response.data['fleet_vehicle'])
        self.assertEqual(response.data['fleet_vehicle']['registration_number'], 'A123BC77')

    def test_manual_create_without_known_vehicle(self):
        response = self.client.post(
            self.list_url,
            {
                'registration_number': 'X999XX99',
                'direction': GatePassDirection.EXIT,
                'passed_at': '2026-06-24T08:15:22+03:00',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['fleet_vehicle'])

    def test_list_filters_by_direction(self):
        VehicleGatePass.objects.create(
            terminal=self.terminal, registration_number='A111AA11',
            direction=GatePassDirection.ENTRY, passed_at='2026-06-24T08:00:00+03:00',
            source=GatePassSource.MANUAL,
        )
        VehicleGatePass.objects.create(
            terminal=self.terminal, registration_number='B222BB22',
            direction=GatePassDirection.EXIT, passed_at='2026-06-24T09:00:00+03:00',
            source=GatePassSource.MANUAL,
        )
        response = self.client.get(self.list_url, {'direction': GatePassDirection.EXIT})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['registration_number'], 'B222BB22')

    def test_dispatcher_cannot_edit_via_unsupported_method(self):
        gate_pass = VehicleGatePass.objects.create(
            terminal=self.terminal, registration_number='A111AA11',
            direction=GatePassDirection.ENTRY, passed_at='2026-06-24T08:00:00+03:00',
            source=GatePassSource.MACROSCOP,
        )
        response = self.client.patch(f'{self.list_url}{gate_pass.pk}/', {'direction': GatePassDirection.EXIT})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
