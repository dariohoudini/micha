from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from .models import ShippingAddress, DeliveryZone
from apps.users.permissions import IsNotSuspended


class ShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = [
            'id', 'label', 'full_name', 'phone',
            'address_line', 'city', 'province',
            'postal_code', 'country', 'is_default', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class DeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = [
            'id', 'city', 'province', 'shipping_cost',
            'estimated_days_min', 'estimated_days_max',
        ]


class ShippingAddressListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/shipping/addresses/"""
    serializer_class = ShippingAddressSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_queryset(self):
        return ShippingAddress.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ShippingAddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/DELETE /api/shipping/addresses/<id>/"""
    serializer_class = ShippingAddressSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_queryset(self):
        return ShippingAddress.objects.filter(user=self.request.user)


class SetDefaultAddressView(APIView):
    """PATCH /api/shipping/addresses/<id>/set-default/"""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def patch(self, request, pk):
        addr = get_object_or_404(ShippingAddress, pk=pk, user=request.user)
        addr.is_default = True
        addr.save()
        return Response({"detail": "Default address updated."})


class DeliveryZoneListView(generics.ListAPIView):
    """GET /api/shipping/zones/ — Public list of delivery zones and costs."""
    serializer_class = DeliveryZoneSerializer
    permission_classes = [permissions.AllowAny]
    queryset = DeliveryZone.objects.filter(is_active=True)


class ShippingCostEstimateView(APIView):
    """GET /api/shipping/estimate/?city=Luanda — Get shipping cost for a city."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        city = request.query_params.get('city', '').strip()
        if not city:
            return Response({"detail": "City parameter is required."}, status=400)
        try:
            zone = DeliveryZone.objects.get(city__iexact=city, is_active=True)
            return Response(DeliveryZoneSerializer(zone).data)
        except DeliveryZone.DoesNotExist:
            return Response({
                "city": city,
                "shipping_cost": 0,
                "estimated_days_min": 3,
                "estimated_days_max": 7,
                "note": "Shipping cost will be confirmed by seller."
            })
