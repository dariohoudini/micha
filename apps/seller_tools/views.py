"""Seller Tools — REST endpoints under /api/v1/seller-tools/."""
from datetime import date, datetime

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    CommissionStatement, ListingQualityScore, PriceCompetitivenessSnapshot,
    ProductComplianceLabel, SellerBroadcast,
    SellerBulkEditJob, SellerHolidayMode, SellerReturnPolicy,
    SellerToolsKpiSnapshot, SellerVatRegistration, StoreFollower,
)


class IsSeller(permissions.BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (
            getattr(u, 'is_staff', False)
            or getattr(u, 'role', '') == 'seller'
            or u.stores.exists()))


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_staff)


def _product_owned(request, product_id):
    from apps.products.models import Product
    return Product.objects.filter(
        id=product_id, store__owner=request.user).first()


# ── CH3 Bulk edit ─────────────────────────────────────────────────────

class BulkEditView(APIView):
    permission_classes = [IsSeller]

    def post(self, request):
        action_type = request.data.get('action_type')
        if action_type not in dict(SellerBulkEditJob.ACTION_CHOICES):
            return Response({'error': 'invalid action_type'},
                            status=status.HTTP_400_BAD_REQUEST)
        listing_ids = request.data.get('listing_ids') or []
        if not isinstance(listing_ids, list) or not listing_ids:
            return Response({'error': 'listing_ids required'},
                            status=status.HTTP_400_BAD_REQUEST)
        job = services.run_bulk_edit(
            request.user, action_type=action_type,
            action_params=request.data.get('action', {}) or
            request.data.get('action_params', {}),
            listing_ids=[int(i) for i in listing_ids[:10000]])
        return Response({'job_id': job.id, 'status': job.status,
                         'succeeded': job.succeeded, 'failed': job.failed,
                         'revertible_until': job.revertible_until},
                        status=status.HTTP_201_CREATED)


class BulkEditRevertView(APIView):
    permission_classes = [IsSeller]

    def post(self, request, job_id):
        result = services.revert_bulk_edit(request.user, int(job_id))
        code = status.HTTP_200_OK if result['reverted'] \
            else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


# ── CH8 Return policy ─────────────────────────────────────────────────

class ReturnPolicyView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        return Response({'policies': [
            {'id': p.id, 'name': p.policy_name, 'scope': p.applicable_to,
             'window_days': p.return_window_days,
             'free_returns': p.free_returns,
             'accepts_if': p.accepts_returns_if}
            for p in SellerReturnPolicy.objects.filter(
                seller=request.user, is_active=True)]})

    def post(self, request):
        try:
            policy = services.create_return_policy(
                request.user,
                policy_name=request.data.get('policy_name', 'Default'),
                applicable_to=request.data.get('applicable_to', 'all'),
                category_ids=request.data.get('category_ids'),
                product_ids=request.data.get('product_ids'),
                return_window_days=request.data.get('return_window_days', 15),
                accepts_returns_if=request.data.get('accepts_returns_if',
                                                    'any_reason'),
                return_shipping_paid_by=request.data.get(
                    'return_shipping_paid_by', 'buyer'),
                refund_to=request.data.get('refund_to', 'original_payment'),
                non_returnable_reasons=request.data.get(
                    'non_returnable_reasons'),
            )
        except ValueError as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'id': policy.id}, status=status.HTTP_201_CREATED)


# ── CH9 Holiday mode ──────────────────────────────────────────────────

class HolidayModeView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        hm = SellerHolidayMode.objects.filter(seller=request.user).first()
        if not hm:
            return Response({'enabled': False})
        return Response({'enabled': hm.enabled, 'start_date': hm.start_date,
                         'end_date': hm.end_date, 'message': hm.message})

    def patch(self, request):
        if not request.data.get('enabled', True):
            services.resume_holiday_mode(request.user)
            return Response({'enabled': False})
        try:
            start = date.fromisoformat(str(request.data.get('start_date')))
            end = date.fromisoformat(str(request.data.get('end_date')))
        except (ValueError, TypeError):
            return Response({'error': 'start_date and end_date required (ISO)'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            services.activate_holiday_mode(
                request.user, start_date=start, end_date=end,
                message=request.data.get('message', ''),
                notify_followers=bool(request.data.get('notify_followers', True)))
        except ValueError as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'enabled': True}, status=status.HTTP_200_OK)


# ── CH10 Q&A helpfulness ──────────────────────────────────────────────

class QaVoteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, qa_id):
        result = services.vote_qa_helpful(
            request.user, int(qa_id),
            helpful=bool(request.data.get('helpful', True)))
        return Response(result, status=status.HTTP_201_CREATED)


# ── CH11 Followers + broadcast ────────────────────────────────────────

class FollowStoreView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, seller_id):
        from django.contrib.auth import get_user_model
        seller = get_user_model().objects.filter(id=seller_id).first()
        if not seller:
            return Response({'error': 'seller not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(services.follow_store(request.user, seller),
                        status=status.HTTP_201_CREATED)

    def delete(self, request, seller_id):
        from django.contrib.auth import get_user_model
        seller = get_user_model().objects.filter(id=seller_id).first()
        if seller:
            services.unfollow_store(request.user, seller)
        return Response({'following': False})


class BroadcastView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        return Response({'broadcasts': [
            {'id': b.id, 'subject': b.subject, 'status': b.status,
             'recipients': b.recipients_count, 'delivered': b.delivered_count,
             'opens': b.open_count, 'clicks': b.click_count,
             'sent_at': b.sent_at}
            for b in SellerBroadcast.objects.filter(
                seller=request.user)[:50]]})

    def post(self, request):
        subject = request.data.get('subject', '').strip()
        body = request.data.get('message_body', '').strip()
        if not subject or not body:
            return Response({'error': 'subject and message_body required'},
                            status=status.HTTP_400_BAD_REQUEST)
        scheduled = request.data.get('scheduled_at')
        scheduled_dt = None
        if scheduled:
            try:
                scheduled_dt = datetime.fromisoformat(scheduled)
            except ValueError:
                pass
        bc = services.send_broadcast(
            request.user, subject=subject, message_body=body,
            coupon_id=str(request.data.get('coupon_id', '')),
            linked_product_ids=request.data.get('linked_product_ids') or [],
            scheduled_at=scheduled_dt)
        return Response({'id': bc.id, 'status': bc.status,
                         'block_reason': bc.block_reason,
                         'delivered': bc.delivered_count},
                        status=status.HTTP_201_CREATED)


# ── CH12 Commission statement ─────────────────────────────────────────

class CommissionStatementView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        qs = CommissionStatement.objects.filter(seller=request.user)
        if request.query_params.get('year'):
            qs = qs.filter(period_year=request.query_params['year'])
        return Response({'statements': [
            {'id': s.id, 'period': f'{s.period_year}-{s.period_month:02d}',
             'reference': s.reference_number,
             'net_payout_cents': s.net_payout_cents, 'status': s.status,
             'pdf_key': s.pdf_key, 'csv_key': s.csv_key}
            for s in qs[:36]]})

    def post(self, request):  # generate on demand
        year = int(request.data.get('year') or date.today().year)
        month = int(request.data.get('month') or date.today().month)
        s = services.generate_commission_statement(request.user, year, month)
        return Response({'id': s.id, 'net_payout_cents': s.net_payout_cents,
                         'order_count': s.order_count},
                        status=status.HTTP_201_CREATED)


# ── CH13 Listing quality score ────────────────────────────────────────

class ListingQualityView(APIView):
    permission_classes = [IsSeller]

    def get(self, request, product_id):
        p = _product_owned(request, int(product_id))
        if not p:
            return Response({'error': 'product not found'},
                            status=status.HTTP_404_NOT_FOUND)
        lqs = services.compute_listing_quality_score(p)
        return Response({'total': lqs.total_score, 'breakdown': lqs.breakdown,
                         'missing': lqs.missing})


# ── CH14 Price competitiveness ────────────────────────────────────────

class PriceCompetitivenessView(APIView):
    permission_classes = [IsSeller]

    def get(self, request, product_id):
        p = _product_owned(request, int(product_id))
        if not p:
            return Response({'error': 'product not found'},
                            status=status.HTTP_404_NOT_FOUND)
        snap = services.compute_price_competitiveness(p)
        return Response({
            'seller_price_cents': snap.seller_price_cents,
            'market_median_cents': snap.market_median_cents,
            'market_p25_cents': snap.market_p25_cents,
            'market_p75_cents': snap.market_p75_cents,
            'position': snap.position_label, 'ratio': snap.position_ratio,
            'sample_size': snap.sample_size, 'suggestion': snap.suggestion})


# ── CH17 VAT ──────────────────────────────────────────────────────────

class VatRegistrationView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        return Response({'registrations': [
            {'id': v.id, 'country': v.country, 'type': v.tax_type,
             'number': v.registration_number, 'status': v.validation_status,
             'display_mode': v.price_display_mode}
            for v in SellerVatRegistration.objects.filter(
                seller=request.user, is_active=True)]})

    def post(self, request):
        country = request.data.get('country', '')
        number = request.data.get('registration_number', '')
        if not country or not number:
            return Response(
                {'error': 'country and registration_number required'},
                status=status.HTTP_400_BAD_REQUEST)
        reg = services.register_vat(
            request.user, country=country, registration_number=number,
            tax_type=request.data.get('tax_type', 'VAT'),
            price_display_mode=request.data.get('price_display_mode',
                                                'inclusive'))
        return Response({'id': reg.id, 'validation_status':
                         reg.validation_status}, status=status.HTTP_201_CREATED)


# ── CH18 Multi-store ──────────────────────────────────────────────────

class LinkedStoresView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        return Response({'seller_ids': services.linked_seller_ids(request.user)})

    def post(self, request):
        from django.contrib.auth import get_user_model
        target = get_user_model().objects.filter(
            id=request.data.get('store_seller_id')).first()
        if not target:
            return Response({'error': 'store_seller_id not found'},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            link = services.link_store(request.user, target,
                                       role=request.data.get('role', 'owner'))
        except ValueError as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'linked': True, 'store_seller_id': target.id},
                        status=status.HTTP_201_CREATED)


# ── CH19 Dispute appeal ───────────────────────────────────────────────

class DisputeAppealView(APIView):
    permission_classes = [IsSeller]

    def post(self, request, dispute_id):
        reason = request.data.get('appeal_reason', '').strip()
        if not reason:
            return Response({'error': 'appeal_reason required'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            appeal = services.file_dispute_appeal(
                request.user, dispute_id=int(dispute_id), appeal_reason=reason,
                evidence_keys=request.data.get('evidence_keys') or [])
        except ValueError as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'id': appeal.id, 'status': appeal.status},
                        status=status.HTTP_201_CREATED)


# ── CH20 Payout config ────────────────────────────────────────────────

class BankAccountView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        from apps.payments.models import SellerBankAccount
        return Response({'accounts': [
            {'id': a.id, 'bank': a.bank_name, 'masked': a.masked_number(),
             'is_default': a.is_default, 'verified': a.is_verified}
            for a in SellerBankAccount.objects.filter(seller=request.user)]})

    def post(self, request):
        required = ['account_holder_name', 'bank_name', 'bank_country',
                    'account_number']
        if any(not request.data.get(f) for f in required):
            return Response({'error': f'required: {required}'},
                            status=status.HTTP_400_BAD_REQUEST)
        acct = services.add_bank_account(
            request.user,
            account_holder_name=request.data['account_holder_name'],
            bank_name=request.data['bank_name'],
            bank_country=request.data['bank_country'],
            account_number=str(request.data['account_number']),
            currency=request.data.get('currency', 'USD'),
            swift_code=request.data.get('swift_code', ''),
            sort_code=request.data.get('sort_code', ''),
            routing_number=request.data.get('routing_number', ''),
            is_default=bool(request.data.get('is_default')))
        return Response({'id': acct.id, 'masked': acct.masked_number()},
                        status=status.HTTP_201_CREATED)


class WithdrawView(APIView):
    permission_classes = [IsSeller]

    def post(self, request):
        try:
            amount = int(request.data.get('amount_cents'))
        except (TypeError, ValueError):
            return Response({'error': 'amount_cents required'},
                            status=status.HTTP_400_BAD_REQUEST)
        result = services.request_withdrawal(
            request.user, amount_cents=amount,
            destination=request.data.get('destination', 'alipay'))
        return Response(result, status=status.HTTP_201_CREATED)


# ── CH22 Compliance labels ────────────────────────────────────────────

class ComplianceLabelView(APIView):
    permission_classes = [IsSeller]

    def post(self, request, product_id):
        if not _product_owned(request, int(product_id)):
            return Response({'error': 'product not found'},
                            status=status.HTTP_404_NOT_FOUND)
        label_type = request.data.get('label_type')
        if label_type not in dict(ProductComplianceLabel.LABEL_CHOICES):
            return Response({'error': 'invalid label_type'},
                            status=status.HTTP_400_BAD_REQUEST)
        label = services.add_compliance_label(
            request.user, product_id=int(product_id), label_type=label_type,
            label_value=request.data.get('label_value', ''),
            issuing_body=request.data.get('issuing_body', ''),
            certificate_key=request.data.get('certificate_key', ''))
        return Response({'id': label.id,
                         'verification': label.verification_status},
                        status=status.HTTP_201_CREATED)


# ── CH23 API quota ────────────────────────────────────────────────────

class QuotaStatusView(APIView):
    permission_classes = [IsSeller]

    def get(self, request):
        return Response(services.quota_status(request.user))


# ── CH24 KPI dashboard ────────────────────────────────────────────────

class KpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'snapshots': [
            {'date': s.snapshot_date,
             'bulk_import_success_pct': s.bulk_import_success_pct,
             'bulk_edit_success_pct': s.bulk_edit_success_pct,
             'dispute_self_resolution_pct': s.dispute_self_resolution_pct,
             'qa_answer_rate_pct': s.qa_answer_rate_pct,
             'avg_listing_quality': s.avg_listing_quality,
             'broadcast_engagement_pct': s.broadcast_engagement_pct,
             'price_competitive_pct': s.price_competitive_pct,
             'shipping_template_coverage_pct': s.shipping_template_coverage_pct,
             'academy_m1_completion_pct': s.academy_m1_completion_pct}
            for s in SellerToolsKpiSnapshot.objects.order_by(
                '-snapshot_date')[:30]]})

    def post(self, request):
        snap = services.snapshot_seller_tools_kpis()
        return Response({'date': snap.snapshot_date},
                        status=status.HTTP_201_CREATED)
