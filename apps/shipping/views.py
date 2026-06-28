from rest_framework.permissions import AllowAny
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from .models import ShippingAddress, DeliveryZone, ShippingTemplate, ShippingMethod
from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser


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
    permission_classes = [AllowAny]
    queryset = DeliveryZone.objects.filter(is_active=True)


class ShippingMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingMethod
        fields = ['id', 'service', 'custom_service_name', 'destinations',
                  'min_days', 'max_days', 'free_shipping', 'cost',
                  'additional_item_cost', 'ordering']
        read_only_fields = ['id']


class ShippingTemplateSerializer(serializers.ModelSerializer):
    methods = ShippingMethodSerializer(many=True, required=False)

    class Meta:
        model = ShippingTemplate
        fields = ['id', 'name', 'ship_from_country', 'processing_days',
                  'is_default', 'methods', 'created_at']
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        methods = validated_data.pop('methods', [])
        tpl = ShippingTemplate.objects.create(**validated_data)
        for i, m in enumerate(methods):
            ShippingMethod.objects.create(template=tpl, ordering=i, **m)
        return tpl

    def update(self, instance, validated_data):
        methods = validated_data.pop('methods', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if methods is not None:
            instance.methods.all().delete()
            for i, m in enumerate(methods):
                ShippingMethod.objects.create(template=instance, ordering=i, **m)
        return instance


class ShippingTemplateListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/shipping/templates/ — seller's reusable templates."""
    serializer_class = ShippingTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return ShippingTemplate.objects.filter(seller=self.request.user).prefetch_related('methods')

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user)


class ShippingTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/PUT/DELETE /api/v1/shipping/templates/<id>/"""
    serializer_class = ShippingTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return ShippingTemplate.objects.filter(seller=self.request.user).prefetch_related('methods')


class ReverseGeocodeView(APIView):
    """GET /api/v1/shipping/geocode/reverse/?lat=&lng= — best-effort.

    User Process Flow §9.2 asks for "Use My Location" to fill the
    address form. Online vendors (Google, Mapbox) require keys we
    don't have wired. We provide a *bounded* mapping: Angola-only
    province inference from lat/lng using rough centroids. Good
    enough to autofill the province dropdown; the user still types
    the street.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]
    # Rough centroids for Angolan provinces. Picks nearest.
    _CENTROIDS = [
        ('Luanda',        -8.83,  13.24),
        ('Bengo',         -8.50,  13.50),
        ('Cuanza Norte',  -9.20,  14.85),
        ('Cuanza Sul',   -10.74,  13.95),
        ('Malanje',       -9.55,  16.34),
        ('Lunda Norte',   -8.40,  20.34),
        ('Lunda Sul',     -9.65,  20.42),
        ('Uíge',          -7.61,  15.06),
        ('Zaire',         -6.13,  12.37),
        ('Cabinda',       -5.55,  12.20),
        ('Cuando Cubango',-14.66, 17.69),
        ('Cunene',       -16.60, 16.20),
        ('Huíla',        -14.93, 13.49),
        ('Namibe',       -15.20, 12.15),
        ('Benguela',     -12.58, 13.41),
        ('Huambo',       -12.78, 15.74),
        ('Bié',          -12.39, 17.05),
        ('Moxico',       -11.78, 20.74),
    ]

    def get(self, request):
        try:
            lat = float(request.query_params.get('lat') or 0)
            lng = float(request.query_params.get('lng') or 0)
        except ValueError:
            return Response({'error': 'lat/lng required'}, status=400)
        if not lat or not lng:
            return Response({'error': 'lat/lng required'}, status=400)
        # Pick nearest centroid by haversine-ish (flat-Earth OK at AO scale).
        best = min(self._CENTROIDS, key=lambda c: (c[1] - lat) ** 2 + (c[2] - lng) ** 2)
        province, _, _ = best
        # User Process Flow §20.8 — log geocode lookups too.
        try:
            from apps.analytics.models import UserEvent
            UserEvent.objects.create(
                user=request.user, event='addresses.geocode',
                properties={'province': province, 'lat': lat, 'lng': lng},
                ip=(request.META.get('REMOTE_ADDR') or None),
            )
        except Exception:
            pass
        return Response({
            'province': province,
            'city': province,  # FE will show this as a suggestion
            'address_line': '',
        })


class ShippingCostEstimateView(APIView):
    """GET /api/shipping/estimate/?city=Luanda — Get shipping cost for a city."""
    permission_classes = [AllowAny]

    def get(self, request):
        city = request.query_params.get('city', '').strip()
        if not city:
            return Response({'error': 'City parameter is required.'}, status=400)
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
