
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import ContentFlag, IPBan, BuyerProtectionClaim
from apps.users.permissions import IsAdminOrSuperuser, IsNotSuspended

class ContentFlagListView(APIView):
    permission_classes = [IsAdminOrSuperuser]
    def get(self, request):
        flags = ContentFlag.objects.filter(is_resolved=False)
        return Response([{"id":f.id,"target_type":f.target_type,"target_id":f.target_id,"reason":f.reason,"auto":f.auto_flagged,"at":f.created_at} for f in flags])

class ResolveContentFlagView(APIView):
    permission_classes = [IsAdminOrSuperuser]
    def patch(self, request, pk):
        flag = get_object_or_404(ContentFlag, pk=pk)
        flag.is_resolved=True; flag.save()
        return Response({"detail":"Flag resolved."})

class IPBanView(APIView):
    permission_classes = [IsAdminOrSuperuser]
    def get(self, request):
        return Response([{"ip":b.ip_address,"reason":b.reason,"at":b.created_at} for b in IPBan.objects.all()])
    def post(self, request):
        ip = request.data.get("ip_address")
        if not ip: return Response({"detail":"IP required."},status=400)
        IPBan.objects.get_or_create(ip_address=ip,defaults={"reason":request.data.get("reason",""),"banned_by":request.user})
        return Response({"detail":f"IP {ip} banned."})

class BuyerProtectionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]
    def post(self, request):
        from apps.orders.models import Order
        order = get_object_or_404(Order, pk=request.data.get("order_id"), buyer=request.user)
        if hasattr(order,"buyer_protection"): return Response({"detail":"Claim already submitted."},status=400)
        age_days = (timezone.now() - order.created_at).days
        auto = age_days > 30 and order.status not in ("delivered","cancelled")
        claim = BuyerProtectionClaim.objects.create(
            order=order,buyer=request.user,reason=request.data.get("reason",""),
            auto_approved=auto,status="approved" if auto else "pending",
            resolved_at=timezone.now() if auto else None)
        return Response({"detail":"Claim submitted.","auto_approved":auto},status=201)
