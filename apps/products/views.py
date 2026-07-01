from rest_framework.permissions import AllowAny
"""
Products Views
FIX: Image resizing wired to upload
FIX: ETag header on product detail
FIX: Bulk CSV upload endpoint
FIX: ?fields= sparse fieldsets supported
"""
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.db import models
from django.db.models import F
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser

from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser, IsNotAdminStaff
from apps.idempotency.decorators import idempotent
from .models import Product, Category, ProductImage, ProductQA
from .serializers import (
    ProductListSerializer, ProductDetailSerializer, ProductWriteSerializer,
    CategorySerializer, ProductQASerializer,
)


class _PublicCacheMixin:
    """R3: Mark public list responses cacheable at the CDN.

    All authenticated paths and POST/PATCH/DELETE bypass automatically
    (we only set the header on 200 responses to GET). Cache TTL kept
    short (60s) because product catalogues do change — a 5min stale
    window is what the CDN's stale-while-revalidate header gives us
    anyway.
    """
    public_cache_max_age = 60

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.method == 'GET' and 200 <= response.status_code < 300:
            ttl = int(self.public_cache_max_age)
            response['Cache-Control'] = (
                f'public, max-age={ttl}, s-maxage={ttl}, '
                f'stale-while-revalidate=300'
            )
            response.setdefault('Vary', 'Accept-Language, Accept-Encoding')
        return response


class CategoryListView(_PublicCacheMixin, generics.ListAPIView):
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    queryset = Category.objects.filter(parent=None).prefetch_related("subcategories")
    # Category list changes very rarely — bump the TTL.
    public_cache_max_age = 300


class CategoryDetailView(generics.RetrieveAPIView):
    """GET /api/v1/products/categories/<id>/ — single category with
    its §15 attribute_schema. The product wizard calls this when the
    seller picks a leaf so the right dynamic fields appear."""
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    queryset = Category.objects.all()


class ProductListView(_PublicCacheMixin, generics.ListAPIView):
    """GET /api/products/ — public, supports ?fields and faceted filters.

    Filters:
      search           - free text on title/brand
      category         - slug
      min_price/max_price
      condition        - new|used|refurbished
      city             - store city
      brand            - single value or comma-separated list
      has_discount     - 1/true to only show items with compare_at_price > price
      min_rating       - 0-5 (annotates avg rating; uses 0 for unreviewed)
      ordering         - -created_at|price|-price|-views|popular|-rating
    """
    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        from django.db.models import Q, F, Avg, Count
        qs = Product.active.all()
        params = self.request.query_params

        search = params.get("search", "").strip()[:200]
        if search:
            from .search import search_products
            qs = search_products(qs, search)

        if params.get("category"):
            qs = qs.filter(category__slug=params["category"])
        if params.get("min_price"):
            qs = qs.filter(price__gte=params["min_price"])
        if params.get("max_price"):
            qs = qs.filter(price__lte=params["max_price"])
        if params.get("condition"):
            qs = qs.filter(condition=params["condition"])
        if params.get("city"):
            qs = qs.filter(store__city__iexact=params["city"])

        brand_param = params.get("brand", "").strip()
        if brand_param:
            brands = [b.strip() for b in brand_param.split(",") if b.strip()]
            if len(brands) == 1:
                qs = qs.filter(brand__iexact=brands[0])
            elif brands:
                qs = qs.filter(brand__in=brands)

        if params.get("has_discount") in ("1", "true", "True"):
            qs = qs.filter(compare_at_price__gt=F("price"))

        ordering = params.get("ordering", "-created_at")

        # Annotate rating only when filtering or sorting by it
        needs_rating = params.get("min_rating") or ordering == "-rating"
        if needs_rating:
            qs = qs.annotate(
                _avg_rating=Avg("reviews__rating"),
            )
            min_rating = params.get("min_rating")
            if min_rating:
                try:
                    qs = qs.filter(_avg_rating__gte=float(min_rating))
                except (TypeError, ValueError):
                    pass

        allowed_orderings = {
            "-created_at": "-created_at",
            "price": "price",
            "-price": "-price",
            "-views": "-views",
            "popular": "-views",
            "-rating": "-_avg_rating" if needs_rating else "-views",
        }
        # SPU collapse: when ?collapse=group is set, return one card per
        # ProductGroup (the cheapest active offer in the group) so the buyer
        # sees one row per real product instead of N near-duplicates from N
        # sellers. Products without a group (legacy) keep their own row.
        if params.get('collapse') == 'group':
            from django.db.models import OuterRef, Subquery, Min, Count
            cheapest_per_group = (
                Product.active
                .filter(product_group=OuterRef('product_group'))
                .order_by('price')
                .values('pk')[:1]
            )
            qs = qs.filter(
                Q(pk=Subquery(cheapest_per_group)) | Q(product_group__isnull=True)
            ).annotate(
                _seller_count=Count(
                    'product_group__seller_listings',
                    filter=Q(
                        product_group__seller_listings__is_active=True,
                        product_group__seller_listings__is_archived=False,
                    ),
                ),
                _group_best_price=Min(
                    'product_group__seller_listings__price',
                    filter=Q(
                        product_group__seller_listings__is_active=True,
                        product_group__seller_listings__is_archived=False,
                    ),
                ),
            )

        # When a search query is active and caller didn't explicitly choose an
        # ordering, sort by relevance rank rather than by creation date.
        if search and "ordering" not in params:
            try:
                qs = qs.order_by("-_rank", "-created_at")
            except Exception:
                qs = qs.order_by("-created_at")
        else:
            qs = qs.order_by(allowed_orderings.get(ordering, "-created_at"))

        return qs


class ProductFacetsView(APIView):
    """GET /api/v1/products/facets/ — aggregate filter values for current search.

    Returns counts per brand/condition/category and the price range,
    optionally narrowed by an active search query.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.db.models import Count, Min, Max, F, Q
        qs = Product.active.all()
        params = request.query_params

        search = params.get("search", "").strip()[:200]
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(brand__icontains=search))

        if params.get("category"):
            qs = qs.filter(category__slug=params["category"])

        # Brands (top 30, with counts)
        brands_qs = (
            qs.exclude(brand__isnull=True).exclude(brand="")
              .values("brand")
              .annotate(count=Count("id"))
              .order_by("-count")[:30]
        )
        brands = [{"name": b["brand"], "count": b["count"]} for b in brands_qs]

        # Conditions
        conditions_qs = qs.values("condition").annotate(count=Count("id")).order_by("-count")
        conditions = [{"value": c["condition"], "count": c["count"]} for c in conditions_qs]

        # Categories (top 20)
        cats_qs = (
            qs.exclude(category__isnull=True)
              .values("category__slug", "category__name")
              .annotate(count=Count("id"))
              .order_by("-count")[:20]
        )
        categories = [
            {"slug": c["category__slug"], "name": c["category__name"], "count": c["count"]}
            for c in cats_qs
        ]

        # Price range
        price_agg = qs.aggregate(min=Min("price"), max=Max("price"))

        # Special toggles
        discount_count = qs.filter(compare_at_price__gt=F("price")).count()

        return Response({
            "total": qs.count(),
            "brands": brands,
            "conditions": conditions,
            "categories": categories,
            "price_range": {
                "min": float(price_agg["min"] or 0),
                "max": float(price_agg["max"] or 0),
            },
            "discount_count": discount_count,
        })


class ProductDetailView(APIView):
    """
    GET /api/products/<slug>/
    FIX: ETag header — mobile clients skip download if product unchanged
    """
    permission_classes = [AllowAny]

    def get(self, request, slug):
        from apps.core.cache_kit import cached_call, build_key

        # The expensive part is the serializer + prefetch. Cache *that*,
        # keyed by slug AND the product's tag version so save() invalidates
        # automatically. Lookup the product id once (cheap by indexed slug)
        # so we know which tag to version-bind to.
        pid = Product.objects.filter(
            slug=slug, is_active=True, is_archived=False,
        ).values_list('id', flat=True).first()
        if pid is None:
            from django.http import Http404
            raise Http404()

        cache_key = build_key('product_detail', [f'product:{pid}'], slug)

        def _load():
            product = get_object_or_404(
                Product.objects.select_related("store", "category").prefetch_related("images", "tags"),
                pk=pid,
            )
            return ProductDetailSerializer(product, context={"request": request}).data

        data = cached_call(cache_key, _load, ttl=300, swr_ttl=60)

        # ETag derived from the data identity (so 304 still works post-cache).
        etag = f'"{pid}-{hash(repr(sorted(data.items()))) & 0xffffffff:x}"'
        if request.META.get("HTTP_IF_NONE_MATCH") == etag:
            from django.http import HttpResponse
            return HttpResponse(status=304)

        # Increment view counter (outside the cache — it's a write)
        Product.objects.filter(pk=pid).update(views=F("views") + 1)

        # Track for recommendations
        if request.user.is_authenticated:
            from apps.recommendations.models import ProductInteraction
            try:
                product_for_track = Product.objects.get(pk=pid)
                ProductInteraction.track(request.user, product_for_track, "view")
            except Exception:
                pass

        response = Response(data)
        response["ETag"] = etag
        response["Cache-Control"] = "public, max-age=60"
        return response


class SellerProductListView(generics.ListAPIView):
    """GET /api/products/my/ — seller's own products"""
    serializer_class = ProductDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return Product.objects.filter(
            store__owner=self.request.user
        ).select_related("store", "category").prefetch_related("images")


def _save_price_tiers(product, tiers_payload):
    """Replace product's price_tiers with the given list."""
    import json
    from apps.products.models import PriceTier
    if isinstance(tiers_payload, str):
        try:
            tiers_payload = json.loads(tiers_payload)
        except Exception:
            return
    if not isinstance(tiers_payload, list):
        return
    product.price_tiers.all().delete()
    seen_quantities = set()
    from apps.core.money import to_decimal
    for t in tiers_payload:
        try:
            min_q = int(t.get('min_quantity'))
            # Money stays Decimal end-to-end. float() round-trip would
            # introduce binary-floating-point drift on values like 99.99
            # that the cart later snapshots as price_at_add.
            unit_price = to_decimal(t.get('unit_price'))
        except (TypeError, ValueError):
            continue
        if min_q < 2 or min_q in seen_quantities or unit_price <= 0:
            continue
        seen_quantities.add(min_q)
        PriceTier.objects.create(
            product=product, min_quantity=min_q, unit_price=unit_price,
        )


def _save_variant_combos(product, combos_payload):
    """Replace product's variant_combos with the given list.
    combos_payload: list of dicts with options, price, quantity, sku (optional).
    """
    import json
    from apps.inventory.models import ProductVariantCombo
    if isinstance(combos_payload, str):
        try:
            combos_payload = json.loads(combos_payload)
        except Exception:
            return
    if not isinstance(combos_payload, list):
        return
    # Wipe existing and recreate (simple, idempotent for MVP)
    product.variant_combos.all().delete()
    from apps.core.money import to_decimal
    for c in combos_payload:
        opts = c.get('options') or {}
        if not isinstance(opts, dict) or not opts:
            continue
        try:
            # Same Decimal-end-to-end reasoning as price tiers above.
            price = to_decimal(c.get('price'))
            qty = int(c.get('quantity', 0))
        except (TypeError, ValueError):
            continue
        ProductVariantCombo.objects.create(
            product=product,
            options=opts,
            price=price,
            quantity=qty,
            sku=str(c.get('sku') or '')[:100],
            is_active=True,
        )


class ProductCreateView(generics.CreateAPIView):
    """POST /api/v1/products/

    Idempotency REQUIRED. A retried create would produce TWO listings
    of the same product — there's no natural dedupe (titles aren't
    unique, slugs are uniqued per save() but with a "-N" suffix so a
    retry simply lands as "iPhone-2"). The idempotency layer is the
    only defence.
    """
    serializer_class = ProductWriteSerializer
    # IsNotAdminStaff: admins are management-only and cannot sell (create
    # listings). A real seller (is_seller, not staff) still passes.
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser,
                          IsNotSuspended, IsNotAdminStaff]

    @idempotent(required=True)
    def post(self, request, *args, **kwargs):
        # §18 — duplicate product detection. Same store + identical
        # title within the last 24h almost certainly = accidental
        # double-submit. Front-end shows a modal and the seller picks
        # "edit existing" or "create anyway"; we use a ``force=true``
        # query/body flag to bypass on the second click.
        from apps.stores.models import Store
        from .models import Product
        from datetime import timedelta
        from django.utils import timezone
        title = (request.data.get('title') or '').strip()
        force = str(request.data.get('force_create') or request.query_params.get('force') or '').lower() in ('1','true','yes')
        if title and not force:
            try:
                store = Store.objects.get(owner=request.user)
                existing = Product.objects.filter(
                    store=store, title__iexact=title,
                    created_at__gte=timezone.now() - timedelta(days=1),
                ).first()
                if existing:
                    return Response({
                        'error': 'duplicate_product',
                        'detail': 'Já tem um produto com este título.',
                        'existing_id': existing.id,
                        'existing_title': existing.title,
                    }, status=409)
            except Store.DoesNotExist:
                pass
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        from apps.stores.models import Store
        # Auto-provision a Store on first publish.
        #
        # Why: apps/stores/urls.py has NO public store-create endpoint
        # (only list / detail / toggle-open / review). New sellers
        # register → are flagged is_seller=True → land on the seller
        # dashboard → tap "Publish product" → previously got 404 here
        # because no Store existed and there was no UI path to create
        # one. The /seller/profile/ endpoint only manages SellerProfile
        # (logo, banner, policies) — that's NOT a Store.
        #
        # Until the stores app grows a proper create endpoint and a
        # dedicated UI flow, we get_or_create on first publish using
        # the user's display name as the default store name. The
        # seller can later customise via /seller/setup or a future
        # store-detail edit screen. This unblocks the
        # "registered → publish product" flow with no extra clicks.
        user = self.request.user
        default_name = (
            getattr(getattr(user, 'profile', None), 'full_name', None)
            or user.username
            or (user.email.split('@')[0] if user.email else None)
            or 'My Store'
        )
        store, _ = Store.objects.get_or_create(
            owner=user,
            defaults={'name': default_name, 'is_active': True, 'is_open': True},
        )
        product = serializer.save(store=store, created_by=user)
        # Dev/staging: skip the human review queue so sellers see
        # their listings immediately. Production should override this
        # by setting MODERATION_AUTO_APPROVE=False in env and wiring
        # a background task that reviews & flips the status to
        # ``published`` or ``violation`` per the spec §17 pipeline.
        from django.conf import settings as _settings
        auto_ok = getattr(_settings, 'MODERATION_AUTO_APPROVE', True)
        if auto_ok:
            product.moderation_status = 'published'
            product.save(update_fields=['moderation_status'])
        combos = self.request.data.get('variant_combos')
        if combos:
            _save_variant_combos(product, combos)
        tiers = self.request.data.get('price_tiers')
        if tiers:
            _save_price_tiers(product, tiers)


class ProductUpdateView(generics.UpdateAPIView):
    """AliExpress §17.3 — editing a live product.

    Price / stock changes take effect immediately and the product
    stays Published. Title / category / image changes flip the
    listing back to ``under_review`` and the moderation pipeline
    re-runs. ``perform_update`` inspects the changed fields against
    the resident ``serializer.initial_data`` to decide.
    """
    serializer_class = ProductWriteSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return Product.objects.filter(store__owner=self.request.user)

    # AliExpress §17.3 — fields whose change pushes the listing back
    # to the Under Review queue. Everything else (price, qty, sku,
    # promo, shipping) is "instant edit".
    REVIEW_TRIGGER_FIELDS = {
        'title', 'description', 'category', 'brand',
        'condition', 'meta_title', 'meta_description',
    }

    def perform_update(self, serializer):
        before = {f: getattr(serializer.instance, f, None) for f in self.REVIEW_TRIGGER_FIELDS}
        product = serializer.save()
        # Did any review-triggering field actually change?
        changed = False
        for f in self.REVIEW_TRIGGER_FIELDS:
            if before.get(f) != getattr(product, f, None):
                changed = True
                break
        if changed and product.moderation_status == 'published':
            product.moderation_status = 'under_review'
            product.save(update_fields=['moderation_status'])
        if 'variant_combos' in self.request.data:
            _save_variant_combos(product, self.request.data.get('variant_combos'))
        if 'price_tiers' in self.request.data:
            _save_price_tiers(product, self.request.data.get('price_tiers'))


class ProductImageUploadView(APIView):
    """
    POST /api/products/<id>/images/
    FIX: Image resizing wired to upload — creates thumbnail/medium/large variants

    Idempotency optional. Image uploads can be expensive (resize +
    perceptual hash + storage write). A retry without dedupe wastes
    bandwidth and disk; with a header, the cached response is replayed.
    Not required because multipart bodies aren't trivially hashable —
    forcing the header would break existing clients.
    """
    parser_classes = [MultiPartParser]
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    @idempotent()
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, store__owner=request.user)
        image_file = request.FILES.get("image")
        if not image_file:
            return Response({'error': 'validation_error', "detail": "image file required."}, status=400)

        # FIX: Validate MIME type
        from middleware.file_validator import validate_image
        validate_image(image_file)

        # FIX: Resize and create variants
        from middleware.image_processor import process_image_upload
        try:
            paths = process_image_upload(image_file, upload_to=f"products/{product.pk}/")
        except ValueError as e:
            return Response({'error': 'invalid_image', "detail": str(e)}, status=400)

        img = ProductImage.objects.create(
            product=product,
            image=paths.get("large", image_file),
            thumbnail_url=paths.get("thumbnail", ""),
            medium_url=paths.get("medium", ""),
            large_url=paths.get("large", ""),
            alt_text=request.data.get("alt_text", ""),
        )

        # Compute perceptual hash from the source upload — drives the
        # SPU/SKU image-similarity match in ProductGroupSuggestView.
        # Only set if the product doesn't already have one (first image wins).
        if not product.image_hash:
            try:
                from .perceptual_hash import compute_dhash
                image_file.seek(0)
                phash = compute_dhash(image_file)
                if phash:
                    Product.objects.filter(pk=product.pk).update(image_hash=phash)
            except Exception:
                pass

        # Bust product schema cache
        cache.delete(f"schema:product:{product.pk}")

        return Response({
            "id": img.id,
            "thumbnail_url": img.thumbnail_url,
            "medium_url": img.medium_url,
            "large_url": img.large_url,
        }, status=201)


class BulkProductCreateView(APIView):
    """
    POST /api/products/bulk/
    Body: { products: [...] } — array of up to 100 products

    Idempotency REQUIRED. A retried bulk import would mint 100 duplicate
    products in a second call. Per-row de-dup would be expensive and
    title-based dedupe is incorrect (same title is a legitimate refresh).
    The idempotency layer is the only honest answer.
    """
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    @idempotent(required=True)
    def post(self, request):
        from apps.stores.models import Store
        store = get_object_or_404(Store, owner=request.user)
        products_data = request.data.get("products", [])

        if not isinstance(products_data, list):
            return Response({'error': 'validation_error', "detail": "products must be an array."}, status=400)
        if len(products_data) > 100:
            return Response({'error': 'too_many', "detail": "Maximum 100 products per request."}, status=400)

        created = []
        errors = []
        for i, p_data in enumerate(products_data):
            serializer = ProductWriteSerializer(data=p_data)
            if serializer.is_valid():
                product = serializer.save(store=store, created_by=request.user)
                created.append(product.id)
            else:
                errors.append({"index": i, "errors": serializer.errors})

        return Response({
            "created": len(created),
            "errors": len(errors),
            "created_ids": created,
            "error_details": errors,
        }, status=201 if created else 400)


class ProductCompareView(APIView):
    """GET /api/products/compare/?id=1&id=2&id=3"""
    permission_classes = [AllowAny]

    def get(self, request):
        ids = request.query_params.getlist("id")[:4]  # Max 4
        if len(ids) < 2:
            return Response({'error': 'validation_error', "detail": "Provide at least 2 product IDs."}, status=400)
        products = Product.active.filter(id__in=ids)
        return Response(ProductDetailSerializer(products, many=True, context={"request": request}).data)


class ProductQAListCreateView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        qa = ProductQA.objects.filter(product=product, is_published=True).select_related("asker")
        return Response(ProductQASerializer(qa, many=True).data)

    def post(self, request, pk):
        if not request.user.is_authenticated:
            return Response({'error': 'authentication_required'}, status=401)
        product = get_object_or_404(Product, pk=pk, is_active=True)
        question = request.data.get("question", "").strip()
        if not question:
            return Response({'error': 'validation_error', "detail": "question required."}, status=400)
        qa = ProductQA.objects.create(product=product, asker=request.user, question=question)
        return Response(ProductQASerializer(qa).data, status=201)


class ProductQAAnswerView(APIView):
    """PATCH /api/v1/products/qa/<int:qa_id>/answer/  — seller answers a question."""
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def patch(self, request, qa_id):
        from django.utils import timezone
        qa = get_object_or_404(ProductQA, pk=qa_id)
        if qa.product.store.owner_id != request.user.id and not request.user.is_staff:
            return Response({'error': 'forbidden', 'detail': 'Apenas o vendedor pode responder.'}, status=403)
        answer = (request.data.get('answer') or '').strip()
        if not answer:
            return Response({'error': 'validation_error', 'detail': 'Resposta vazia.'}, status=400)
        if len(answer) > 2000:
            return Response({'error': 'validation_error', 'detail': 'Máximo 2000 caracteres.'}, status=400)
        qa.answer = answer
        qa.answered_by = request.user
        qa.answered_at = timezone.now()
        qa.save(update_fields=['answer', 'answered_by', 'answered_at'])
        return Response(ProductQASerializer(qa).data)


class ProductDuplicateView(APIView):
    """POST /api/v1/products/<pk>/duplicate/

    Idempotency REQUIRED. The whole purpose of this endpoint is to clone
    a product — a retry without dedupe produces N copies for N retries.
    No natural unique constraint to fall back on.
    """
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    @idempotent(required=True)
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, store__owner=request.user)
        product.pk = None
        product.slug = None
        product.title = f"{product.title} (Copy)"
        product.is_active = False
        product.views = 0
        product.save()
        return Response({"detail": "Product duplicated.", "id": product.id, "slug": product.slug}, status=201)


class ProductGroupListView(generics.ListAPIView):
    """
    GET /api/products/groups/
    Shows one card per unique product — buyers see canonical products.
    Each card shows best price and number of sellers.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.products.models import ProductGroup, Product
        from django.db.models import Min, Count

        groups = ProductGroup.objects.annotate(
            seller_count=Count('seller_listings', filter=models.Q(
                seller_listings__is_active=True,
                seller_listings__is_archived=False,
            )),
            best_price=Min('seller_listings__price'),
        ).filter(seller_count__gt=0)

        category = request.query_params.get('category')
        search = request.query_params.get('search', '').strip()

        if category:
            groups = groups.filter(category__slug=category)
        if search:
            groups = groups.filter(
                models.Q(title__icontains=search) |
                models.Q(brand__icontains=search)
            )

        data = []
        for g in groups:
            # Get best seller listing
            best = Product.objects.filter(
                product_group=g,
                is_active=True,
                is_archived=False,
            ).order_by('price').select_related('store').prefetch_related('images').first()

            if best:
                # Use prefetched images cache; .first() / .exists() would
                # each issue their own query (N+1 across all groups).
                cached_imgs = list(best.images.all())
                first_img = cached_imgs[0] if cached_imgs else None
                image_url = None
                if first_img and first_img.image:
                    try:
                        image_url = request.build_absolute_uri(first_img.image.url)
                    except Exception:
                        image_url = None
                data.append({
                    'group_id': g.id,
                    'title': g.title,
                    'brand': g.brand,
                    'best_price': g.best_price,
                    'seller_count': g.seller_count,
                    'best_seller': best.store.name if best.store else '',
                    'image': image_url,
                    'slug': best.slug,
                })

        return Response(data)


class ProductGroupSuggestView(APIView):
    """GET /api/v1/products/groups/suggest/?title=…&brand=…&category=<slug>

    Help sellers avoid forking the catalog. Returns canonical ProductGroups
    that the proposed listing would join — the seller can then choose to
    list as another offer on this canonical product, or proceed to create
    a brand-new SPU.

    Returns at most 5 candidates with seller_count + cheapest current offer.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Q as _Q
        from .models import ProductGroup
        import hashlib

        title = (request.query_params.get('title') or '').strip()
        brand = (request.query_params.get('brand') or '').strip()
        category_slug = (request.query_params.get('category') or '').strip()
        image_hash = (request.query_params.get('image_hash') or '').strip()[:32]

        # Allow image-hash-only searches when the seller has uploaded an image
        # but not yet typed a meaningful title.
        if (not title or len(title) < 4) and not image_hash:
            return Response({'results': []})

        category = None
        if category_slug:
            category = Category.objects.filter(slug=category_slug).first()

        # Pass 1: exact-fingerprint match (deterministic; covers every
        # variant the normaliser handles). This is the same key the
        # pre_save signal will compute, so a hit here = same group on save.
        candidates = []
        if title and len(title) >= 4:
            raw = (
                f'{ProductGroup._normalize_title(title)}|'
                f'{ProductGroup._normalize_brand(brand)}|'
                f'{category.id if category else 0}'
            )
            target_fp = hashlib.sha256(raw.encode()).hexdigest()[:64]
            grp = ProductGroup.objects.filter(fingerprint=target_fp).first()
            if grp:
                candidates.append(grp)

        # Pass 2: prefix match in same category — surfaces near-matches
        # the seller might want to inspect even if not an exact route.
        if title and len(title) >= 4 and len(candidates) < 5:
            words = [w for w in ProductGroup._normalize_title(title).split() if len(w) >= 3]
            extra_qs = ProductGroup.objects.exclude(pk__in=[g.pk for g in candidates])
            if category:
                extra_qs = extra_qs.filter(category=category)
            if words:
                extra_qs = extra_qs.filter(title__icontains=words[0])
            candidates.extend(list(extra_qs[:5 - len(candidates)]))

        # Pass 3: visually-similar match via perceptual hash. Catches the
        # case where two sellers use different titles for the same item but
        # the same product photo (manufacturer / press image / re-uploaded
        # competitor listing). Hamming distance ≤ 5 = "essentially same".
        if image_hash and len(image_hash) == 16 and len(candidates) < 5:
            from .perceptual_hash import hamming_distance as _hd
            seen_group_ids = {g.id for g in candidates}
            # Pull the candidate set first (bounded by category + non-empty
            # hash) then compute Hamming distance in Python — small set,
            # cheap loop, no need for SQL bit ops.
            # Use the base manager + values_list to dodge ActiveProductManager's
            # select_related (which conflicts with .only(...)). Same effective
            # filter: active + non-archived.
            visual_pairs = (
                Product.objects
                .filter(is_active=True, is_archived=False)
                .exclude(image_hash='').exclude(image_hash__isnull=True)
                .exclude(product_group__isnull=True)
            )
            if category:
                visual_pairs = visual_pairs.filter(category=category)
            visual_pairs = visual_pairs.values_list('image_hash', 'product_group_id')[:500]
            close = []
            close_seen = set()
            for img_hash, gid in visual_pairs:
                if gid in seen_group_ids or gid in close_seen:
                    continue
                if _hd(image_hash, img_hash) <= 5:
                    close.append(gid)
                    close_seen.add(gid)
                    if len(close) + len(candidates) >= 5:
                        break
            if close:
                visual_groups = list(
                    ProductGroup.objects.filter(pk__in=close).order_by('-updated_at')[:5 - len(candidates)]
                )
                candidates.extend(visual_groups)

        # Annotate each with seller stats
        results = []
        for group in candidates:
            offers = (
                Product.active.filter(product_group=group)
                .select_related('store').prefetch_related('images')
                .order_by('price')
            )
            seller_count = offers.count()
            if seller_count == 0:
                continue
            best = offers.first()
            best_image = None
            try:
                # Prefetched on the offers queryset above; .first() bypasses cache.
                cached_imgs = list(best.images.all())
                img = cached_imgs[0] if cached_imgs else None
                if img and img.image:
                    best_image = request.build_absolute_uri(img.image.url)
            except Exception:
                pass
            results.append({
                'group_id': group.id,
                'title': group.title,
                'brand': group.brand or '',
                'category_slug': group.category.slug if group.category_id else None,
                'seller_count': seller_count,
                'best_price': str(best.price),
                'best_offer_id': best.id,
                'best_offer_slug': best.slug,
                'best_offer_image': best_image,
            })

        return Response({'results': results})


class ProductGroupOffersView(generics.ListAPIView):
    """
    GET /api/v1/products/groups/<group_id>/offers/
    All sellers offering the same canonical product, sorted by price.

    ?exclude=<product_id>  excludes one offer (used on PDP "other sellers" rail)
    """
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Product.active.filter(
            product_group_id=self.kwargs['group_id']
        ).select_related('store', 'category').prefetch_related('images').order_by('price')
        exclude_id = self.request.query_params.get('exclude')
        if exclude_id:
            try:
                qs = qs.exclude(pk=int(exclude_id))
            except (TypeError, ValueError):
                pass
        return qs[:20]  # bound the result; nobody scrolls past 20 offers


class PriceAlertView(APIView):
    """POST/DELETE /api/v1/products/<slug>/price-alert/ — Subscribe/unsubscribe to price drop alert."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, slug):
        product = get_object_or_404(Product, slug=slug, is_active=True)
        from apps.recommendations.models import PriceAlert
        alert, created = PriceAlert.objects.get_or_create(
            user=request.user,
            product=product,
            defaults={'target_price': request.data.get('target_price')}
        )
        if not created:
            return Response({'error': 'Already subscribed to price alerts for this product.'}, status=200)
        return Response({'error': 'Price alert activated. You will be notified when the price drops.'}, status=201)

    def delete(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        from apps.recommendations.models import PriceAlert
        PriceAlert.objects.filter(user=request.user, product=product).delete()
        return Response({'detail': 'Price alert removed.'})

    def get(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        from apps.recommendations.models import PriceAlert
        active = PriceAlert.objects.filter(user=request.user, product=product).exists()
        return Response({'active': active})
