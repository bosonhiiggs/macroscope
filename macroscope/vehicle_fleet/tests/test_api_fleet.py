from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from terminal.models import Terminal
from vehicle_fleet.models import FleetVehicle


class FleetVehicleApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='dispatcher', password='pass12345')
        self.client.force_authenticate(self.user)
        self.terminal = Terminal.objects.create(name='Терминал 1', slug='term-1')
        self.other_terminal = Terminal.objects.create(name='Терминал 2', slug='term-2')
        self.list_url = f'/api/terminals/{self.terminal.pk}/fleet-vehicles/'

    def test_create_fleet_vehicle_normalizes_number(self):
        response = self.client.post(
            self.list_url,
            {'registration_number': 'a 123 bc-77', 'brand': 'КамАЗ', 'model': '54901'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['registration_number'], 'A123BC77')
        self.assertTrue(
            FleetVehicle.objects.filter(terminal=self.terminal, registration_number='A123BC77').exists(),
        )

    def test_duplicate_registration_number_returns_400(self):
        FleetVehicle.objects.create(terminal=self.terminal, registration_number='A123BC77')
        response = self.client.post(self.list_url, {'registration_number': 'A123BC77'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_number_allowed_on_different_terminal(self):
        FleetVehicle.objects.create(terminal=self.other_terminal, registration_number='A123BC77')
        response = self.client.post(self.list_url, {'registration_number': 'A123BC77'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_delete_is_soft(self):
        vehicle = FleetVehicle.objects.create(terminal=self.terminal, registration_number='A123BC77')
        response = self.client.delete(f'{self.list_url}{vehicle.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        vehicle.refresh_from_db()
        self.assertFalse(vehicle.is_active)
        self.assertTrue(FleetVehicle.objects.filter(pk=vehicle.pk).exists())

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(None)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
