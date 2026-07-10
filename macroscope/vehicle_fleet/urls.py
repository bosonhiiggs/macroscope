from django.urls import path

from vehicle_fleet import views

urlpatterns = [
    path('fleet-vehicles/', views.FleetVehicleListCreateView.as_view(), name='fleet-vehicle-list'),
    path('fleet-vehicles/<int:pk>/', views.FleetVehicleDetailView.as_view(), name='fleet-vehicle-detail'),
    path('vehicle-gate-passes/', views.VehicleGatePassListCreateView.as_view(), name='gate-pass-list'),
    path('vehicle-gate-passes/<int:pk>/', views.VehicleGatePassDetailView.as_view(), name='gate-pass-detail'),
    path('gate-cameras/sync/', views.GateCameraSyncView.as_view(), name='gate-camera-sync'),
    path('gate-cameras/', views.GateCameraListCreateView.as_view(), name='gate-camera-list'),
    path('gate-cameras/<int:pk>/', views.GateCameraDetailView.as_view(), name='gate-camera-detail'),
]
