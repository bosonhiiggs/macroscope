from django.contrib import admin

from vehicle_fleet.models import (
    FleetVehicle,
    GateCamera,
    MacroscopIntegrationState,
    VehicleGatePass,
)


@admin.register(FleetVehicle)
class FleetVehicleAdmin(admin.ModelAdmin):
    list_display = ('id', 'terminal', 'registration_number', 'brand', 'model', 'is_active')
    list_filter = ('terminal', 'is_active')
    search_fields = ('registration_number', 'brand', 'model')


@admin.register(GateCamera)
class GateCameraAdmin(admin.ModelAdmin):
    list_display = ('id', 'terminal', 'name', 'macroscop_channel_id', 'role', 'is_active')
    list_filter = ('terminal', 'role', 'is_active')


@admin.register(VehicleGatePass)
class VehicleGatePassAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'terminal', 'registration_number', 'direction', 'source', 'passed_at', 'reliability',
    )
    list_filter = ('terminal', 'direction', 'source')
    search_fields = ('registration_number', 'macroscop_event_id')
    readonly_fields = ('raw_event',)


@admin.register(MacroscopIntegrationState)
class MacroscopIntegrationStateAdmin(admin.ModelAdmin):
    list_display = ('terminal', 'is_connected', 'last_event_at', 'last_archive_poll_at')
