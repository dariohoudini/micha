from rest_framework import generics, permissions
from .models import Review
from .serializers import ReviewSerializer
from apps.users.permissions import IsNotSuspended

class ReviewCreateView(generics.CreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]


class SellerReviewListView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Review.objects.filter(seller_id=self.kwargs["seller_id"])
