
from rest_framework import generics, permissions
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
    """Buyer opens a dispute on a shipped/delivered order.

    Delegates to disputes.service.open_dispute so the full side-effect
    set (evidence snapshot + EarningsHold freeze + outbox publish) runs
    atomically. Direct ORM .create() would skip the freeze and let the
    seller cash out mid-dispute.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        from apps.orders.models import Order
        from .service import (
            open_dispute, DisputeError, DisputeAlreadyOpen, InvalidDisputeAction,
        )

        order = get_object_or_404(
            Order, pk=request.data.get("order_id"), buyer=request.user,
        )
        try:
            dispute = open_dispute(
                buyer=request.user,
                order=order,
                reason=request.data.get("reason", "other"),
                description=request.data.get("description", ""),
            )
        except DisputeAlreadyOpen as e:
            return Response({'error': 'dispute_already_open', 'detail': str(e)}, status=409)
        except InvalidDisputeAction as e:
            return Response({'error': 'invalid_dispute_action', 'detail': str(e)}, status=400)
        except DisputeError as e:
            return Response({'error': 'dispute_error', 'detail': str(e)}, status=400)

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
    """Post a message to a dispute thread.

    Delegates to disputes.service.add_message which updates the
    last_seller_message_at SLA marker when the seller posts.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, pk):
        from .service import (
            add_message, DisputeError, NotADisputeParticipant, InvalidDisputeAction,
        )
        d = get_object_or_404(Dispute, pk=pk)
        try:
            msg = add_message(
                actor=request.user,
                dispute=d,
                body=request.data.get("message", ""),
                attachment=request.FILES.get("attachment"),
            )
        except NotADisputeParticipant as e:
            return Response({'error': 'not_a_participant', 'detail': str(e)}, status=403)
        except InvalidDisputeAction as e:
            return Response({'error': 'invalid_dispute_action', 'detail': str(e)}, status=400)
        except DisputeError as e:
            return Response({'error': 'dispute_error', 'detail': str(e)}, status=400)
        return Response(MsgSerializer(msg).data, status=201)

class MyDisputesView(generics.ListAPIView):
    """List disputes where the caller is EITHER party.

    The buyer-only filter shipped originally meant sellers had no way to
    enumerate disputes opened against them — they had to know dispute
    IDs out-of-band, which made the seller dashboard impossible to
    build. Include both sides; the detail view already participant-
    checks, so widening the list view does not weaken authorization.
    """
    serializer_class = DisputeSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        from django.db.models import Q
        return Dispute.objects.filter(
            Q(buyer=self.request.user) | Q(seller=self.request.user)
        )

class AdminDisputeListView(generics.ListAPIView):
    serializer_class = DisputeSerializer
    permission_classes = [IsAdminOrSuperuser]
    def get_queryset(self):
        qs = Dispute.objects.all()
        s = self.request.query_params.get("status")
        if s: qs = qs.filter(status=s)
        return qs

class AdminResolveDisputeView(APIView):
    """Admin applies a resolution to a dispute.

    Delegates to disputes.service.resolve_dispute which atomically:
      • flips status to resolved + records resolution + admin_note
      • settles EarningsHold rows (release / refund) based on outcome
      • creates a Refund row with status='pending' when buyer money
        is owed (NOT 'processed' — the PSP path picks it up)
      • clears SLA timers
      • publishes dispute.resolved to outbox
    """
    permission_classes = [IsAdminOrSuperuser]

    def patch(self, request, pk):
        from .service import (
            resolve_dispute, DisputeError, InvalidDisputeAction,
        )
        d = get_object_or_404(Dispute, pk=pk)
        try:
            d = resolve_dispute(
                admin=request.user,
                dispute=d,
                resolution=request.data.get("resolution", ""),
                note=request.data.get("note", ""),
                refund_amount=request.data.get("refund_amount"),
            )
        except InvalidDisputeAction as e:
            return Response({'error': 'invalid_resolution', 'detail': str(e)}, status=400)
        except DisputeError as e:
            return Response({'error': 'dispute_error', 'detail': str(e)}, status=400)
        return Response({'detail': f'Resolved: {d.resolution}.', 'status': d.status})

class FraudFlagView(APIView):
    permission_classes = [IsAdminOrSuperuser]
    def get(self, request):
        flags = FraudFlag.objects.filter(is_resolved=False)
        return Response([{"id":f.id,"user":f.user.email,"reason":f.reason,"at":f.created_at} for f in flags])
    def patch(self, request, pk):
        f = get_object_or_404(FraudFlag, pk=pk)
        f.is_resolved=True; f.save()
        return Response({"detail":"Resolved."})
