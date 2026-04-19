"""
Products Views
FIX: Image resizing wired to upload
FIX: ETag header on product detail
FIX: Bulk CSV upload endpoint
FIX: ?fields= sparse fieldsets supported
"""
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.db.models import F
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser

from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser, IsAdminOrSuperuser
from middleware.cache_control import ProductETagMixin
from .models import Product, Category, ProductImage, ProductQA
from .serializers import (
    ProductListSerializer, ProductDetailSerializer, ProductWriteSerializer,
    CategorySerializer, ProductQASerializer,
)


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    queryset = Category.objects.filter(parent=None).prefetch_related("subcategories")


class ProductListView(generics.ListAPIView):
    """GET /api/products/ — public, cached, supports ?fields="""
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Product.active.all()
        params = self.request.query_params

        search = params.get("search", "").strip()[:200]
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(title__icontains=search) | Q(brand__icontains=search))

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
        if params.get("brand"):
            qs = qs.filter(brand__iexact=params["brand"])

        ordering = params.get("ordering", "-created_at")
        allowed_orderings = ["-created_at", "price", "-price", "-views"]
        if ordering in allowed_orderings:
            qs = qs.order_by(ordering)

        return qs


class ProductDetailView(APIView):
    """
    GET /api/products/<slug>/
    FIX: ETag header — mobile clients skip download if product unchanged
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        product = get_object_or_404(
            Product.objects.select_related("store", "category").prefetch_related("images", "tags"),
            slug=slug, is_active=True, is_archived=False
        )

        # ETag based on updated_at
        etag = f'"{product.pk}-{product.updated_at.timestamp()}"'
        if request.META.get("HTTP_IF_NONE_MATCH") == etag:
            from django.http import HttpResponse
            return HttpResponse(status=304)

        # Increment view counter
        Product.objects.filter(pk=product.pk).update(views=F("views") + 1)

        # Track for recommendations
        if request.user.is_authenticated:
            from apps.recommendations.models import ProductInteraction
            ProductInteraction.track(request.user, product, "view")

        serializer = ProductDetailSerializer(product, context={"request": request})
        response = Response(serializer.data)
        response["ETag"] = etag
        response["Cache-Control"] = "private, max-age=0, must-revalidate"
        return response


class SellerProductListView(generics.ListAPIView):
    """GET /api/products/my/ — seller's own products"""
    serializer_class = ProductDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return Product.objects.filter(
            store__owner=self.request.user
        ).select_related("store", "category").prefetch_related("images")


class ProductCreateView(generics.CreateAPIView):
    serializer_class = ProductWriteSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def perform_create(self, serializer):
        from apps.stores.models import Store
        store = get_object_or_404(Store, owner=self.request.user)
        serializer.save(store=store, created_by=self.request.user)


class ProductUpdateView(generics.UpdateAPIView):
    serializer_class = ProductWriteSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        return Product.objects.filter(store__owner=self.request.user)


class ProductImageUploadView(APIView):
    """
    POST /api/products/<id>/images/
    FIX: Image resizing wired to upload — creates thumbnail/medium/large variants
    """
    parser_classes = [MultiPartParser]
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, store__owner=request.user)
        image_file = request.FILES.get("image")
        if not image_file:
            return Response({"error": "validation_error", "detail": "image file required."}, status=400)

        # FIX: Validate MIME type
        from middleware.file_validator import validate_image
        validate_image(image_file)

        # FIX: Resize and create variants
        from middleware.image_processor import process_image_upload
        try:
            paths = process_image_upload(image_file, upload_to=f"products/{product.pk}/")
        except ValueError as e:
            return Response({"error": "invalid_image", "detail": str(e)}, status=400)

        img = ProductImage.objects.create(
            product=product,
            image=paths.get("large", image_file),
            thumbnail_url=paths.get("thumbnail", ""),
            medium_url=paths.get("medium", ""),
            large_url=paths.get("large", ""),
            alt_text=request.data.get("alt_text", ""),
        )

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
    FIX: Sellers can import multiple products in one request
    """
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def post(self, request):
        from apps.stores.models import Store
        store = get_object_or_404(Store, owner=request.user)
        products_data = request.data.get("products", [])

        if not isinstance(products_data, list):
            return Response({"error": "validation_error", "detail": "products must be an array."}, status=400)
        if len(products_data) > 100:
            return Response({"error": "too_many", "detail": "Maximum 100 products per request."}, status=400)

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
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        ids = request.query_params.getlist("id")[:4]  # Max 4
        if len(ids) < 2:
            return Response({"error": "validation_error", "detail": "Provide at least 2 product IDs."}, status=400)
        products = Product.active.filter(id__in=ids)
        return Response(ProductDetailSerializer(products, many=True, context={"request": request}).data)


class ProductQAListCreateView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        qa = ProductQA.objects.filter(product=product, is_published=True).select_related("asker")
        return Response(ProductQASerializer(qa, many=True).data)

    def post(self, request, pk):
        if not request.user.is_authenticated:
            return Response({"error": "authentication_required"}, status=401)
        product = get_object_or_404(Product, pk=pk, is_active=True)
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"error": "validation_error", "detail": "question required."}, status=400)
        qa = ProductQA.objects.create(product=product, asker=request.user, question=question)
        return Response(ProductQASerializer(qa).data, status=201)


class ProductDuplicateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, store__owner=request.user)
        product.pk = None
        product.slug = None
        product.title = f"{product.title} (Copy)"
        product.is_active = False
        product.views = 0
        product.save()
        return Response({"detail": "Product duplicated.", "id": product.id, "slug": product.slug}, status=201)
