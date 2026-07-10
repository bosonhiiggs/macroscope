from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from terminal.models import Terminal
from vehicle_fleet.constants import GatePassSource
from vehicle_fleet.models import FleetVehicle, GateCamera, VehicleGatePass
from vehicle_fleet.serializers import (
    FleetVehicleSerializer,
    GateCameraSerializer,
    VehicleGatePassSerializer,
)
from vehicle_fleet.services import FleetVehicleService, PlateNormalizer


class TerminalScopedMixin:
    def get_terminal(self):
        return get_object_or_404(Terminal, pk=self.kwargs['terminal_pk'])


class FleetVehicleListCreateView(TerminalScopedMixin, generics.ListCreateAPIView):
    serializer_class = FleetVehicleSerializer

    def get_queryset(self):
        qs = FleetVehicle.objects.filter(terminal=self.get_terminal())
        params = self.request.query_params
        if params.get('search'):
            qs = qs.filter(registration_number__icontains=PlateNormalizer.normalize(params['search']))
        if params.get('is_active') is not None:
            qs = qs.filter(is_active=params['is_active'].lower() in ('1', 'true'))
        return qs.order_by('registration_number')

    def perform_create(self, serializer):
        serializer.save(terminal=self.get_terminal())


class FleetVehicleDetailView(TerminalScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FleetVehicleSerializer

    def get_queryset(self):
        return FleetVehicle.objects.filter(terminal=self.get_terminal())

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class VehicleGatePassListCreateView(TerminalScopedMixin, generics.ListCreateAPIView):
    serializer_class = VehicleGatePassSerializer

    def get_queryset(self):
        qs = VehicleGatePass.objects.filter(
            terminal=self.get_terminal(),
        ).select_related('fleet_vehicle', 'gate_camera')
        params = self.request.query_params
        if params.get('date_from'):
            qs = qs.filter(passed_at__gte=params['date_from'])
        if params.get('date_to'):
            qs = qs.filter(passed_at__lte=params['date_to'])
        if params.get('direction'):
            qs = qs.filter(direction=params['direction'])
        if params.get('registration_number'):
            qs = qs.filter(
                registration_number__icontains=PlateNormalizer.normalize(params['registration_number']),
            )
        if params.get('fleet_vehicle_id'):
            qs = qs.filter(fleet_vehicle_id=params['fleet_vehicle_id'])
        if params.get('source'):
            qs = qs.filter(source=params['source'])
        return qs

    def perform_create(self, serializer):
        terminal = self.get_terminal()
        registration_number = serializer.validated_data['registration_number']
        fleet_vehicle = FleetVehicleService.find_for_terminal(terminal, registration_number)
        serializer.save(
            terminal=terminal,
            source=GatePassSource.MANUAL,
            fleet_vehicle=fleet_vehicle,
            created_by=self.request.user,
        )


class VehicleGatePassDetailView(TerminalScopedMixin, generics.RetrieveAPIView):
    serializer_class = VehicleGatePassSerializer

    def get_queryset(self):
        return VehicleGatePass.objects.filter(
            terminal=self.get_terminal(),
        ).select_related('fleet_vehicle', 'gate_camera')


class GateCameraListCreateView(TerminalScopedMixin, generics.ListCreateAPIView):
    serializer_class = GateCameraSerializer

    def get_queryset(self):
        return GateCamera.objects.filter(terminal=self.get_terminal())

    def perform_create(self, serializer):
        serializer.save(terminal=self.get_terminal())


class GateCameraDetailView(TerminalScopedMixin, generics.RetrieveUpdateAPIView):
    serializer_class = GateCameraSerializer

    def get_queryset(self):
        return GateCamera.objects.filter(terminal=self.get_terminal())


class GateCameraSyncView(TerminalScopedMixin, APIView):
    """Подтянуть список камер из Macroscop /api/channels.

    Заглушка: реальный запрос появится после MacroscopHttpClient (этап 5 плана).
    """

    def post(self, request, terminal_pk):
        return Response(
            {'detail': 'Синхронизация камер появится после реализации MacroscopHttpClient.'},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
