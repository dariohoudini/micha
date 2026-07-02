from rest_framework.permissions import AllowAny
from rest_framework import serializers, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Avg
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import Review, ProductReview, ReviewPhoto, ReviewHelpfulVote
from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser

User = get_user_model()


class ReviewPhotoSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ReviewPhoto
        fields = ['id', 'image', 'image_url', 'uploaded_at']

    def get_image_url(self, obj):
        if not obj.image:
            return None
        req = self.context.get('request')
        return req.build_absolute_uri(obj.image.url) if req else obj.image.url


class ReviewSerializer(serializers.ModelSerializer):
    reviewer_email = serializers.ReadOnlyField(source='reviewer.email')
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['id', 'reviewer_email', 'reviewer_name', 'seller', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_reviewer_name(self, obj):
        try:
            return obj.reviewer.profile.full_name
        except Exception:
            return ''

    def validate(self, attrs):
        # Self-review check only applies when seller is being set (create).
        # On update, attrs['seller'] is absent because we strip it below.
        seller = attrs.get('seller')
        if seller is not None and self.context['request'].user == seller:
            raise serializers.ValidationError("You cannot review yourself.")
        return attrs

    def create(self, validated_data):
        validated_data['reviewer'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # ``seller`` is write-once. A reviewer who left a 1-star for seller A
        # must not be able to PATCH the same review to point at seller B,
        # which would silently drag down B's rating without B ever
        # interacting with this reviewer. Strip seller from update payloads.
        validated_data.pop('seller', None)
        return super().update(instance, validated_data)


class ProductReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.SerializerMethodField()
    reviewer_email = serializers.ReadOnlyField(source='reviewer.email')
    photos = ReviewPhotoSerializer(many=True, read_only=True)
    uploaded_photos = serializers.ListField(
        child=serializers.ImageField(), write_only=True, required=False
    )

    class Meta:
        model = ProductReview
        fields = [
            'id', 'reviewer_name', 'reviewer_email',
            'product', 'rating', 'title', 'comment',
            'seller_reply', 'seller_replied_at',
            'helpful_count', 'is_verified_purchase',
            'photos', 'uploaded_photos',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'reviewer_name', 'reviewer_email',
            'seller_reply', 'seller_replied_at',
            'helpful_count', 'is_verified_purchase',
            'created_at', 'updated_at',
        ]

    def get_reviewer_name(self, obj):
        try:
            return obj.reviewer.profile.full_name
        except Exception:
            return ''

    def validate(self, attrs):
        request = self.context['request']
        product = attrs.get('product')
        from apps.orders.models import OrderItem
        has_purchase = OrderItem.objects.filter(
            product=product,
            order__buyer=request.user,
            order__status='delivered'
        ).exists()
        if not has_purchase:
            raise serializers.ValidationError(
                "You can only review products you have purchased and received."
            )
        if ProductReview.objects.filter(reviewer=request.user, product=product).exists():
            raise serializers.ValidationError("You have already reviewed this product.")
        return attrs

    def create(self, validated_data):
        photos_data = validated_data.pop('uploaded_photos', [])
        validated_data['reviewer'] = self.context['request'].user
        validated_data['is_verified_purchase'] = True
        from apps.orders.models import OrderItem
        order_item = OrderItem.objects.filter(
            product=validated_data['product'],
            order__buyer=validated_data['reviewer'],
            order__status='delivered',
        ).first()
        if order_item:
            validated_data['order_item'] = order_item
        review = super().create(validated_data)
        for photo in photos_data:
            ReviewPhoto.objects.create(review=review, image=photo)
        return review


class ReviewCreateView(generics.CreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]


class MyReviewsView(APIView):
    """GET /api/v1/reviews/my-reviews/ — the caller's own reviews.

    The profile screen shows a review count; this endpoint never existed
    so the count silently read 0 forever. Returns both kinds (product +
    seller reviews) with a combined count.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        product_reviews = ProductReview.objects.filter(
            reviewer=request.user).order_by('-created_at')
        seller_reviews = Review.objects.filter(
            reviewer=request.user).order_by('-created_at')
        results = [
            {'id': r.id, 'kind': 'product', 'rating': r.rating,
             'created_at': r.created_at}
            for r in product_reviews[:50]
        ] + [
            {'id': r.id, 'kind': 'seller', 'rating': r.rating,
             'created_at': r.created_at}
            for r in seller_reviews[:50]
        ]
        return Response({'count': product_reviews.count() + seller_reviews.count(),
                         'results': results})


class SellerReviewListView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Review.objects.filter(seller_id=self.kwargs['seller_id'])


class SellerRatingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, seller_id):
        seller = get_object_or_404(User, pk=seller_id)
        result = Review.objects.filter(seller=seller).aggregate(avg=Avg('rating'))
        total = Review.objects.filter(seller=seller).count()
        return Response({
            "seller_id": seller_id,
            "average_rating": round(result['avg'] or 0, 2),
            "total_reviews": total,
        })


class ReviewUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_queryset(self):
        return Review.objects.filter(reviewer=self.request.user)


class ProductReviewCreateView(generics.CreateAPIView):
    serializer_class = ProductReviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]


class ProductReviewListView(generics.ListAPIView):
    """GET /api/v1/reviews/product/<id>/

    Filters:
      rating       - 1..5 (only that rating)
      has_photos   - 1/true → only reviews with photos
    Ordering:
      ordering=-created_at (default), helpful (= -helpful_count), rating, -rating
    """
    serializer_class = ProductReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        from django.db.models import Count
        qs = ProductReview.objects.filter(
            product_id=self.kwargs['product_id']
        ).prefetch_related('photos', 'helpful_votes').annotate(_photo_count=Count('photos'))

        params = self.request.query_params

        rating = params.get('rating')
        if rating:
            try:
                r = int(rating)
                if 1 <= r <= 5:
                    qs = qs.filter(rating=r)
            except (TypeError, ValueError):
                pass

        if params.get('has_photos') in ('1', 'true', 'True'):
            qs = qs.filter(_photo_count__gt=0)

        ordering = params.get('ordering', '-created_at')
        allowed = {
            '-created_at': '-created_at',
            'helpful': '-helpful_count',
            '-helpful_count': '-helpful_count',
            'rating': 'rating',
            '-rating': '-rating',
        }
        return qs.order_by(allowed.get(ordering, '-created_at'))


class ProductRatingView(APIView):
    """GET /api/v1/reviews/product/<id>/rating/

    Returns avg rating, total, rating distribution {1..5}, and with_photos count.
    """
    permission_classes = [AllowAny]

    def get(self, request, product_id):
        from apps.products.models import Product
        from django.db.models import Count
        product = get_object_or_404(Product, pk=product_id)
        base = ProductReview.objects.filter(product=product)

        agg = base.aggregate(avg=Avg('rating'))
        total = base.count()

        # Rating distribution
        dist = {i: 0 for i in range(1, 6)}
        for row in base.values('rating').annotate(count=Count('id')):
            dist[row['rating']] = row['count']

        with_photos_count = base.annotate(_pc=Count('photos')).filter(_pc__gt=0).count()

        return Response({
            "product_id": product_id,
            "average_rating": round(agg['avg'] or 0, 2),
            "total_reviews": total,
            "rating_distribution": dist,
            "with_photos_count": with_photos_count,
        })


class SellerReplyView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def post(self, request, review_id):
        review = get_object_or_404(ProductReview, pk=review_id)
        if review.product.store.owner != request.user:
            return Response({'error': 'Not your product.'}, status=403)
        if review.seller_reply:
            return Response({'error': 'Already replied to this review.'}, status=400)
        reply = request.data.get('reply', '').strip()
        if not reply:
            return Response({'error': 'Reply text is required.'}, status=400)
        review.seller_reply = reply
        review.seller_replied_at = timezone.now()
        review.save()
        return Response({"detail": "Reply posted."})


class VoteReviewHelpfulView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, review_id):
        review = get_object_or_404(ProductReview, pk=review_id)
        if review.reviewer == request.user:
            return Response({'error': 'Cannot vote on your own review.'}, status=400)
        _, created = ReviewHelpfulVote.objects.get_or_create(
            review=review, user=request.user
        )
        if created:
            review.helpful_count += 1
            review.save(update_fields=['helpful_count'])
            return Response({"detail": "Marked as helpful."})
        return Response({'error': 'Already voted.'}, status=200)


class ReviewFlagView(APIView):
    """POST /api/v1/reviews/<pk>/flag/ — Flag a review."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        from apps.reviews.models import ProductReview
        from apps.reviews.flag_models import ReviewFlag
        review = get_object_or_404(ProductReview, pk=pk)
        if ReviewFlag.objects.filter(review=review, flagged_by=request.user).exists():
            return Response({'error': 'Already flagged.'}, status=400)
        ReviewFlag.objects.create(
            review=review,
            flagged_by=request.user,
            reason=request.data.get('reason', 'other'),
            details=request.data.get('details', ''),
        )
        return Response({'error': 'Review flagged for moderation.'}, status=201)
