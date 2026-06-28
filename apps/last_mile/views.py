"""Last-mile — REST endpoints under /api/v1/last-mile/."""
from datetime import date

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    Courier, GpsDeliveryAddress, LastMileKpiSnapshot, LastMileShipment,
)


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_staff)


class IsCourier(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (
            getattr(request.user, 'is_staff', False)
            or hasattr(request.user, 'courier_profile')))


# ── CH2 rate quote (buyer-facing) ─────────────────────────────────────

class RateQuoteView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            rate, zone = services.calculate_shipping_rate(
                request.data.get('origin', 'Luanda'),
                request.data.get('destination'),
                weight_grams=int(request.data.get('weight_grams', 0)),
                length_cm=request.data.get('length_cm', 0),
                width_cm=request.data.get('width_cm', 0),
                height_cm=request.data.get('height_cm', 0),
                payment_method=request.data.get('payment_method', 'prepaid'),
                free_shipping=bool(request.data.get('free_shipping')))
        except services.CODNotAvailable as e:
            return Response({'error': 'cod_not_available', 'province': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'rate_cents': rate, 'zone_class': zone.zone_class,
                         'transit_days': [zone.transit_days_min,
                                          zone.transit_days_max],
                         'cod_available': zone.cod_available})


# ── CH8 available windows ─────────────────────────────────────────────

class WindowsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({'windows': services.available_windows(
            request.query_params.get('origin', 'Luanda'),
            request.query_params.get('destination', 'Luanda'))})


# ── CH3 GPS address ───────────────────────────────────────────────────

class GpsAddressView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({'addresses': [
            {'id': str(a.id), 'label': a.label, 'province': a.province,
             'bairro': a.bairro, 'landmark': a.landmark,
             'quality_score': a.quality_score, 'is_default': a.is_default}
            for a in GpsDeliveryAddress.objects.filter(buyer=request.user)]})

    def post(self, request):
        try:
            addr = services.create_gps_address(
                request.user, province=request.data.get('province'),
                landmark=request.data.get('landmark', ''),
                phone_number=request.data.get('phone_number', ''),
                latitude=request.data.get('latitude'),
                longitude=request.data.get('longitude'),
                municipio=request.data.get('municipio', ''),
                bairro=request.data.get('bairro', ''),
                delivery_notes=request.data.get('delivery_notes', ''),
                label=request.data.get('label', 'Casa'),
                is_default=bool(request.data.get('is_default')))
        except ValueError as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'id': str(addr.id), 'quality_score': addr.quality_score},
                        status=status.HTTP_201_CREATED)


# ── CH13 buyer tracking ───────────────────────────────────────────────

class TrackingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, tracking_id):
        ship = LastMileShipment.objects.filter(
            micha_tracking_id=tracking_id).first()
        if not ship:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({
            'tracking_id': ship.micha_tracking_id, 'status': ship.status,
            'estimated_delivery': ship.estimated_delivery_date,
            'events': [{'status': e.status, 'location': e.location_description,
                        'time': e.event_time} for e in ship.events.all()]})


# ── CH6 POD capture (courier) ─────────────────────────────────────────

class PodCaptureView(APIView):
    permission_classes = [IsCourier]

    def post(self, request, shipment_id):
        ship = LastMileShipment.objects.filter(id=shipment_id).first()
        if not ship:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        result = services.capture_pod(
            ship, photo_key=request.data.get('photo_key', ''),
            otp_entered=request.data.get('otp', ''),
            signature_key=request.data.get('signature_key', ''),
            cod_collected_cents=int(request.data.get('cod_collected_cents', 0)),
            lat=request.data.get('lat'), lng=request.data.get('lng'),
            offline=bool(request.data.get('offline')))
        code = status.HTTP_200_OK if result.get('ok') \
            else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


# ── CH7 failed delivery (courier) ─────────────────────────────────────

class FailDeliveryView(APIView):
    permission_classes = [IsCourier]

    def post(self, request, shipment_id):
        ship = LastMileShipment.objects.filter(id=shipment_id).first()
        if not ship:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        result = services.handle_delivery_failure(
            ship, failure_type=request.data.get('failure_type', 'not_home'),
            notes=request.data.get('notes', ''))
        return Response(result, status=status.HTTP_200_OK)


# ── CH5 courier route ─────────────────────────────────────────────────

class CourierRouteView(APIView):
    permission_classes = [IsCourier]

    def get(self, request, courier_id):
        courier = Courier.objects.filter(id=courier_id).first()
        if not courier:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        route = services.optimise_route(courier)
        if route is None:
            return Response({'stops': []})
        return Response({
            'route_date': route.route_date,
            'total_distance_km': str(route.total_distance_km),
            'stops': [{'sequence': st.sequence,
                       'shipment_id': str(st.shipment_id),
                       'tracking_id': st.shipment.micha_tracking_id,
                       'landmark': st.shipment.address.landmark
                       if st.shipment.address else '',
                       'cod_cents': st.shipment.cod_amount_cents,
                       'leg_km': str(st.leg_distance_km)}
                      for st in route.stops.select_related(
                          'shipment', 'shipment__address')]})


# ── CH24 KPIs ─────────────────────────────────────────────────────────

class KpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'snapshots': [
            {'date': s.snapshot_date,
             'first_attempt_rate_pct': str(s.first_attempt_rate_pct),
             'delivery_success_pct': str(s.delivery_success_pct),
             'on_time_pct': str(s.on_time_pct),
             'failed_buyer_caused_pct': str(s.failed_buyer_caused_pct),
             'weight_discrepancy_pct': str(s.weight_discrepancy_pct),
             'active_couriers': s.active_couriers,
             'by_province': s.by_province}
            for s in LastMileKpiSnapshot.objects.order_by('-snapshot_date')[:30]]})

    def post(self, request):
        snap = services.snapshot_kpis()
        return Response({'date': snap.snapshot_date},
                        status=status.HTTP_201_CREATED)
