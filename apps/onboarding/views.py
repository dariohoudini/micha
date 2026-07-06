"""
First-Run doc CH10 — the guest-profile & onboarding API (all guest,
no account). Keyed by the client device id (AllowAny); PII-free.
"""
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import GuestCartItem, GuestProfile


class GuestProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestProfile
        fields = ['id', 'device_id', 'locale', 'interests', 'permissions',
                  'attribution', 'onboarding_status', 'completed_at',
                  'created_at']
        read_only_fields = ['id', 'onboarding_status', 'completed_at',
                            'created_at']


def _device_id(request):
    return (request.data.get('device_id')
            or request.query_params.get('device_id')
            or '').strip()[:128]


class GuestSessionView(APIView):
    """POST /api/v1/guest/session/ {device_id, attribution?}
    Create-or-return the guest profile for a device (the bootstrap)."""
    permission_classes = [AllowAny]

    def post(self, request):
        device_id = _device_id(request)
        if not device_id:
            return Response({'error': 'device_id required'}, status=400)
        gp, created = GuestProfile.objects.get_or_create(
            device_id=device_id,
            defaults={
                'attribution': request.data.get('attribution') or {},
                # Sensible Angola defaults (ask-little: the common path
                # is a skip; the profile is usable immediately).
                'locale': {'region': 'AO', 'country': 'Angola',
                           'language': 'pt-AO', 'currency': 'AOA'},
            },
        )
        return Response(
            {'guest': GuestProfileSerializer(gp).data, 'new_guest': created},
            status=201 if created else 200)


class GuestProfileView(APIView):
    """GET  /api/v1/guest/profile/?device_id= — read (drives feed/locale)
    PATCH /api/v1/guest/profile/ {device_id, locale?, interests?,
                                  permissions?, attribution?} — write."""
    permission_classes = [AllowAny]

    def get(self, request):
        device_id = _device_id(request)
        gp = GuestProfile.objects.filter(device_id=device_id).first()
        if gp is None:
            return Response({'error': 'not_found'}, status=404)
        return Response(GuestProfileSerializer(gp).data)

    def patch(self, request):
        device_id = _device_id(request)
        if not device_id:
            return Response({'error': 'device_id required'}, status=400)
        gp, _ = GuestProfile.objects.get_or_create(device_id=device_id)

        # Shallow-merge the locale so a partial write (just language)
        # keeps the rest.
        if isinstance(request.data.get('locale'), dict):
            merged = dict(gp.locale or {})
            merged.update({k: v for k, v in request.data['locale'].items()
                           if v is not None})
            gp.locale = merged
        if isinstance(request.data.get('interests'), list):
            # Cap + de-dupe; interests are category ids.
            gp.interests = list(dict.fromkeys(request.data['interests']))[:30]
        if isinstance(request.data.get('permissions'), dict):
            merged = dict(gp.permissions or {})
            merged.update(request.data['permissions'])
            gp.permissions = merged
        if isinstance(request.data.get('attribution'), dict) and not gp.attribution:
            gp.attribution = request.data['attribution']

        if gp.onboarding_status == 'not_started':
            gp.onboarding_status = 'in_progress'
        gp.save()
        return Response(GuestProfileSerializer(gp).data)


class OnboardingInterestsView(APIView):
    """GET /api/v1/onboarding/interests/ — the top-level category grid
    for the cold-start interests question (CH5)."""
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.products.models import Category
        cats = (Category.objects.filter(parent__isnull=True, is_active=True)
                .order_by('name')[:24]
                if hasattr(Category, 'is_active')
                else Category.objects.filter(parent__isnull=True)
                .order_by('name')[:24])
        return Response({'interests': [
            {'id': c.id, 'name': c.name, 'slug': getattr(c, 'slug', '')}
            for c in cats
        ]})


class GuestCartView(APIView):
    """Guest-First doc CH6 — the server-side guest cart.

    PUT /api/v1/guest/cart/ {device_id, items:[{product_id, quantity,
        variant_combo_id?, price_at_add?, title?}]} — replace the guest
        cart snapshot (idempotent by construction: same payload, same
        end state — never a double-quantity).
    GET /api/v1/guest/cart/?device_id= — the snapshot re-validated
        against the live catalog, in the SAME item shape the user cart
        returns so the client hydrates with one code path.
    """
    permission_classes = [AllowAny]

    MAX_ITEMS = 50

    def put(self, request):
        device_id = _device_id(request)
        if not device_id:
            return Response({'error': 'device_id required'}, status=400)
        items_in = request.data.get('items')
        if not isinstance(items_in, list):
            return Response({'error': 'items must be a list'}, status=400)
        gp, _ = GuestProfile.objects.get_or_create(device_id=device_id)

        rows = []
        seen = set()
        for raw in items_in[:self.MAX_ITEMS]:
            try:
                product_id = int(raw.get('product_id'))
                qty = max(1, min(100, int(raw.get('quantity') or 1)))
                combo = raw.get('variant_combo_id') or None
                combo = int(combo) if combo else None
                key = (product_id, combo)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(GuestCartItem(
                    guest=gp, product_id=product_id, variant_combo_id=combo,
                    quantity=qty,
                    price_at_add=raw.get('price_at_add') or raw.get('price'),
                    title=(raw.get('title') or '')[:200],
                ))
            except (TypeError, ValueError, AttributeError):
                continue   # garbage rows in a stale local cart — skip

        gp.cart_items.all().delete()
        GuestCartItem.objects.bulk_create(rows)
        return Response({'saved': len(rows)})

    def get(self, request):
        device_id = _device_id(request)
        gp = GuestProfile.objects.filter(device_id=device_id).first()
        if gp is None:
            return Response({'items': []})
        from apps.products.models import Product
        snapshot = list(gp.cart_items.all())
        products = Product.objects.filter(
            pk__in=[r.product_id for r in snapshot],
            is_active=True, is_archived=False,
        ).in_bulk()
        items = []
        for r in snapshot:
            p = products.get(r.product_id)
            if p is None:
                continue   # gone since the snapshot — recovery skips it
            image = ''
            try:
                first = p.images.first()
                if first and first.image:
                    image = request.build_absolute_uri(first.image.url)
            except Exception:
                pass
            items.append({
                'id': None,                      # no CartItem row yet
                'product': p.id,
                'product_title': p.title,
                'product_price': str(p.price),   # CURRENT price
                'product_image': image,
                'quantity': min(r.quantity, max(p.quantity, 0) or r.quantity),
                'variant_combo': r.variant_combo_id,
            })
        return Response({'items': items})


class OnboardingCompleteView(APIView):
    """POST /api/v1/onboarding/complete/ {device_id, skipped?}
    Mark onboarding done on the guest (CH7) so a returning guest skips
    setup and lands on the feed."""
    permission_classes = [AllowAny]

    def post(self, request):
        device_id = _device_id(request)
        if not device_id:
            return Response({'error': 'device_id required'}, status=400)
        gp, _ = GuestProfile.objects.get_or_create(device_id=device_id)
        gp.onboarding_status = 'skipped' if request.data.get('skipped') else 'completed'
        gp.completed_at = timezone.now()
        gp.save(update_fields=['onboarding_status', 'completed_at', 'updated_at'])
        return Response(GuestProfileSerializer(gp).data)
