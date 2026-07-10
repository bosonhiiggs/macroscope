from rest_framework import serializers

from vehicle_fleet.models import FleetVehicle, GateCamera, VehicleGatePass
from vehicle_fleet.services import FleetVehicleService, PlateNormalizer


class FleetVehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FleetVehicle
        fields = [
            'id', 'registration_number', 'brand', 'model', 'comment', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_registration_number(self, value):
        return PlateNormalizer.normalize(value)

    def validate(self, attrs):
        registration_number = attrs.get('registration_number')
        if registration_number:
            terminal = self.context['view'].get_terminal()
            exclude_id = self.instance.id if self.instance else None
            FleetVehicleService.validate_unique(terminal, registration_number, exclude_id=exclude_id)
        return attrs


class FleetVehicleNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = FleetVehicle
        fields = ['id', 'registration_number']


class GateCameraSerializer(serializers.ModelSerializer):
    class Meta:
        model = GateCamera
        fields = [
            'id', 'macroscop_channel_id', 'name', 'role', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class GateCameraNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = GateCamera
        fields = ['id', 'name', 'role']


class VehicleGatePassSerializer(serializers.ModelSerializer):
    fleet_vehicle = FleetVehicleNestedSerializer(read_only=True)
    gate_camera = GateCameraNestedSerializer(read_only=True)

    class Meta:
        model = VehicleGatePass
        fields = [
            'id', 'registration_number', 'direction', 'passed_at', 'source',
            'reliability', 'recognized_brand', 'recognized_color', 'recognized_type',
            'macroscop_event_id', 'fleet_vehicle', 'gate_camera', 'created_at',
        ]
        read_only_fields = [
            'id', 'source', 'reliability', 'recognized_brand', 'recognized_color',
            'recognized_type', 'macroscop_event_id', 'fleet_vehicle', 'gate_camera', 'created_at',
        ]

    def validate_registration_number(self, value):
        return PlateNormalizer.normalize(value)
