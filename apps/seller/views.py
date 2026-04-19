from rest_framework import generics, permissions, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Avg, F, FloatField
from django.db.models.functions import Coalesce
from .models import SellerProfile, SellerFAQ, SellerAnnouncement, SellerOnboardingChecklist
from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser
from apps.stores.models import Store
from apps.products.models import Product
from apps.reviews.models import Review

class SellerProfileSerializer(serializers.ModelSerializer):
    completion_percentage=serializers.SerializerMethodField()
    class Meta:
        model=SellerProfile
        fields=['store_logo','store_banner','return_policy','shipping_policy','working_hours',
                'is_on_holiday','holiday_message','holiday_until','revenue_goal','subscription_plan',
                'completion_percentage']
    def get_completion_percentage(self,obj):
        try: return obj.seller.onboarding.completion_percentage
        except: return 0

class SellerFAQSerializer(serializers.ModelSerializer):
    class Meta: model=SellerFAQ; fields=['id','question','answer','ordering']
    
class SellerAnnouncementSerializer(serializers.ModelSerializer):
    class Meta: model=SellerAnnouncement; fields=['id','title','message','created_at']

class OnboardingChecklistSerializer(serializers.ModelSerializer):
    completion_percentage=serializers.ReadOnlyField()
    class Meta: model=SellerOnboardingChecklist; fields='__all__'

class SellerProfileView(generics.RetrieveUpdateAPIView):
    serializer_class=SellerProfileSerializer
    permission_classes=[permissions.IsAuthenticated,IsSellerOrSuperuser,IsNotSuspended]
    def get_object(self):
        profile,_=SellerProfile.objects.get_or_create(seller=self.request.user)
        return profile

class SellerDashboardView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsSellerOrSuperuser,IsNotSuspended]
    def get(self,request):
        from apps.orders.models import Order
        user=request.user
        stores=Store.objects.filter(owner=user)
        products=Product.objects.filter(store__owner=user)
        orders=Order.objects.filter(seller=user)
        revenue=orders.filter(payment_status='paid').aggregate(t=Coalesce(Sum('total'),0.0,output_field=FloatField()))['t']
        reviews=Review.objects.filter(seller=user)
        avg_rating=reviews.aggregate(avg=Coalesce(Avg('rating'),0.0))['avg']
        profile,_=SellerProfile.objects.get_or_create(seller=user)
        from apps.analytics.models import SellerPerformance
        perf,_=SellerPerformance.objects.get_or_create(seller=user)
        onboarding,_=SellerOnboardingChecklist.objects.get_or_create(seller=user)
        # Update onboarding
        onboarding.first_store_created=stores.exists()
        onboarding.first_product_added=products.exists()
        onboarding.first_sale_made=orders.filter(status='delivered').exists()
        onboarding.save()
        return Response({
            'welcome':f"Welcome, {user.profile.full_name if hasattr(user,'profile') else user.email}!",
            'tier':perf.tier,
            'performance_score':round(perf.overall_score,2),
            'selfie_reminder':False,
            'stores':stores.count(),
            'products':{'total':products.count(),'active':products.filter(is_active=True).count(),'low_stock':products.filter(quantity__lte=5,is_active=True).count()},
            'orders':{'total':orders.count(),'pending':orders.filter(status='pending').count(),'shipped':orders.filter(status='shipped').count()},
            'revenue':round(float(revenue),2),
            'avg_rating':round(float(avg_rating),2),
            'total_reviews':reviews.count(),
            'onboarding':{'completion':onboarding.completion_percentage,'steps':OnboardingChecklistSerializer(onboarding).data},
            'revenue_goal':str(profile.revenue_goal) if profile.revenue_goal else None,
            'is_on_holiday':profile.is_on_holiday,
        })

class SellerFAQView(generics.ListCreateAPIView):
    serializer_class=SellerFAQSerializer
    permission_classes=[permissions.IsAuthenticated,IsSellerOrSuperuser,IsNotSuspended]
    def get_queryset(self): return SellerFAQ.objects.filter(seller=self.request.user)
    def perform_create(self,s): s.save(seller=self.request.user)

class SellerFAQDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class=SellerFAQSerializer
    permission_classes=[permissions.IsAuthenticated,IsSellerOrSuperuser,IsNotSuspended]
    def get_queryset(self): return SellerFAQ.objects.filter(seller=self.request.user)

class SellerAnnouncementView(generics.ListCreateAPIView):
    serializer_class=SellerAnnouncementSerializer
    permission_classes=[permissions.IsAuthenticated,IsSellerOrSuperuser,IsNotSuspended]
    def get_queryset(self): return SellerAnnouncement.objects.filter(seller=self.request.user)
    def perform_create(self,s): s.save(seller=self.request.user)

class ToggleHolidayModeView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsSellerOrSuperuser,IsNotSuspended]
    def post(self,request):
        profile,_=SellerProfile.objects.get_or_create(seller=request.user)
        profile.is_on_holiday=not profile.is_on_holiday
        profile.holiday_message=request.data.get('message','')
        profile.holiday_until=request.data.get('until')
        profile.save()
        return Response({"is_on_holiday":profile.is_on_holiday,"detail":f"Holiday mode {'enabled' if profile.is_on_holiday else 'disabled'}."})

class OnboardingView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsSellerOrSuperuser]
    def get(self,request):
        checklist,_=SellerOnboardingChecklist.objects.get_or_create(seller=request.user)
        return Response(OnboardingChecklistSerializer(checklist).data)
