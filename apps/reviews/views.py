from rest_framework import serializers, generics, permissions, status
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
    class Meta:
        model = ReviewPhoto
        fields = ['id', 'image', 'uploaded_at']


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
        if self.context['request'].user == attrs.get('seller'):
            raise serializers.ValidationError("You cannot review yourself.")
        return attrs

    def create(self, validated_data):
        validated_data['reviewer'] = self.context['request'].user
        return super().create(validated_data)


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


class SellerReviewListView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Review.objects.filter(seller_id=self.kwargs['seller_id'])


class SellerRatingView(APIView):
    permission_classes = [permissions.AllowAny]

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
    serializer_class = ProductReviewSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return ProductReview.objects.filter(
            product_id=self.kwargs['product_id']
        ).prefetch_related('photos', 'helpful_votes')


class ProductRatingView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, product_id):
        from apps.products.models import Product
        product = get_object_or_404(Product, pk=product_id)
        result = ProductReview.objects.filter(product=product).aggregate(avg=Avg('rating'))
        total = ProductReview.objects.filter(product=product).count()
        return Response({
            "product_id": product_id,
            "average_rating": round(result['avg'] or 0, 2),
            "total_reviews": total,
        })


class SellerReplyView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def post(self, request, review_id):
        review = get_object_or_404(ProductReview, pk=review_id)
        if review.product.store.owner != request.user:
            return Response({"detail": "Not your product."}, status=403)
        if review.seller_reply:
            return Response({"detail": "Already replied to this review."}, status=400)
        reply = request.data.get('reply', '').strip()
        if not reply:
            return Response({"detail": "Reply text is required."}, status=400)
        review.seller_reply = reply
        review.seller_replied_at = timezone.now()
        review.save()
        return Response({"detail": "Reply posted."})


class VoteReviewHelpfulView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, review_id):
        review = get_object_or_404(ProductReview, pk=review_id)
        if review.reviewer == request.user:
            return Response({"detail": "Cannot vote on your own review."}, status=400)
        _, created = ReviewHelpfulVote.objects.get_or_create(
            review=review, user=request.user
        )
        if created:
            review.helpful_count += 1
            review.save(update_fields=['helpful_count'])
            return Response({"detail": "Marked as helpful."})
        return Response({"detail": "Already voted."}, status=200)
