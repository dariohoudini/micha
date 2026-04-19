
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Dispute, DisputeMessage, FraudFlag
from apps.users.permissions import IsNotSuspended, IsAdminOrSuperuser

class MsgSerializer(drf_serializers.ModelSerializer):
    sender_email = drf_serializers.ReadOnlyField(source="sender.email")
    class Meta:
        model = DisputeMessage
        fields = ["id","sender_email","message","attachment","created_at"]
        read_only_fields = ["id","created_at"]

class DisputeSerializer(drf_serializers.ModelSerializer):
    messages = MsgSerializer(many=True, read_only=True)
    buyer_email = drf_serializers.ReadOnlyField(source="buyer.email")
    seller_email = drf_serializers.ReadOnlyField(source="seller.email")
    class Meta:
        model = Dispute
        fields = ["id","order","buyer_email","seller_email","reason","description","status","admin_note","resolution","messages","created_at","updated_at"]
        read_only_fields = ["id","status","admin_note","resolution","created_at","updated_at"]

class OpenDisputeView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]
    def post(self, request):
        from apps.orders.models import Order
        order = get_object_or_404(Order, pk=request.data.get("order_id"), buyer=request.user)
        if hasattr(order,"dispute"): return Response({"detail":"Dispute already open."},status=400)
        if order.status not in ("delivered","shipped"): return Response({"detail":"Can only dispute shipped or delivered orders."},status=400)
        dispute = Dispute.objects.create(order=order,buyer=request.user,seller=order.seller,
            reason=request.data.get("reason","other"),description=request.data.get("description",""))
        return Response(DisputeSerializer(dispute).data, status=201)

class DisputeDetailView(generics.RetrieveAPIView):
    serializer_class = DisputeSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        d = get_object_or_404(Dispute, pk=self.kwargs["pk"])
        if d.buyer != self.request.user and d.seller != self.request.user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied()
        return d

class DisputeMessageView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]
    def post(self, request, pk):
        d = get_object_or_404(Dispute, pk=pk)
        if d.buyer != request.user and d.seller != request.user: return Response({"detail":"Not a participant."},status=403)
        if d.status in ("resolved","closed"): return Response({"detail":"Dispute closed."},status=400)
        msg = DisputeMessage.objects.create(dispute=d,sender=request.user,message=request.data.get("message",""),attachment=request.FILES.get("attachment"))
        return Response(MsgSerializer(msg).data, status=201)

class MyDisputesView(generics.ListAPIView):
    serializer_class = DisputeSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self): return Dispute.objects.filter(buyer=self.request.user)

class AdminDisputeListView(generics.ListAPIView):
    serializer_class = DisputeSerializer
    permission_classes = [IsAdminOrSuperuser]
    def get_queryset(self):
        qs = Dispute.objects.all()
        s = self.request.query_params.get("status")
        if s: qs = qs.filter(status=s)
        return qs

class AdminResolveDisputeView(APIView):
    permission_classes = [IsAdminOrSuperuser]
    def patch(self, request, pk):
        d = get_object_or_404(Dispute, pk=pk)
        res = request.data.get("resolution")
        if res not in ("refund_buyer","pay_seller","partial_refund","dismissed"): return Response({"detail":"Invalid."},status=400)
        d.resolution=res; d.status="resolved"; d.admin_note=request.data.get("note",""); d.resolved_at=timezone.now(); d.save()
        if res == "refund_buyer":
            from apps.orders.models import Refund
            Refund.objects.get_or_create(order=d.order,defaults={"requested_by":d.buyer,"reason":"Admin refund","amount":d.order.total,"status":"processed"})
        return Response({"detail":f"Resolved: {res}."})

class FraudFlagView(APIView):
    permission_classes = [IsAdminOrSuperuser]
    def get(self, request):
        flags = FraudFlag.objects.filter(is_resolved=False)
        return Response([{"id":f.id,"user":f.user.email,"reason":f.reason,"at":f.created_at} for f in flags])
    def patch(self, request, pk):
        f = get_object_or_404(FraudFlag, pk=pk)
        f.is_resolved=True; f.save()
        return Response({"detail":"Resolved."})
