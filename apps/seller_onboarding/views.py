"""
Seller onboarding — REST endpoints
===================================

API surface for the doc's flows. We deliberately split into:

  • Public endpoints — the marketing-funnel forms. Lead capture is
    unauthenticated by design (we don't want to lose leads to a
    login wall).
  • Seller-authenticated endpoints — application progression,
    agreement signing, category enrolment, training, holiday mode,
    reactivation.
  • Admin endpoints — review queues, KYC decisions, brand/category
    approvals.

All write endpoints emit a SellerOnboardingEvent row on success.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    APPLICATION_TRANSITIONS, KycDocument, SellerAgreement,
    SellerApplication, SellerBrand, SellerCategoryEnrolment,
    SellerCategoryUpgradeRequest, SellerCertificate, SellerFeeInvoice,
    SellerHealthScore, SellerHolidayLog, SellerLead,
    SellerOnboardingEvent, SellerReactivationRequest,
    SellerTierHistory, SellerTierState, SellerTrainingProgress,
    SellerVisibilityBoost,
)
from .serializers import (
    KycDocumentSerializer, SellerAgreementSerializer,
    SellerApplicationSerializer, SellerBrandSerializer,
    SellerCategoryEnrolmentSerializer,
    SellerCategoryUpgradeRequestSerializer,
    SellerCertificateSerializer, SellerFeeInvoiceSerializer,
    SellerHealthScoreSerializer, SellerHolidayLogSerializer,
    SellerLeadSerializer, SellerOnboardingEventSerializer,
    SellerReactivationRequestSerializer, SellerTierHistorySerializer,
    SellerTierStateSerializer, SellerTrainingProgressSerializer,
)
from . import services

User = get_user_model()


# ─── Admin permission ────────────────────────────────────────────

class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH1 — Lead capture (public) ─────────────────────────────────

class LeadCreateView(generics.CreateAPIView):
    """POST /api/v1/seller-onboarding/leads/  — anonymous lead form.

    Runs the qualification scoring synchronously so the FE can show
    "you're eligible / we don't serve your country yet" immediately
    instead of after a delayed email."""
    serializer_class = SellerLeadSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        lead = s.save()
        qual = services.submit_lead(lead=lead)
        SellerOnboardingEvent.log(
            kind='lead.created',
            payload={'lead_id': str(lead.id), 'source': lead.lead_source},
        )
        return Response({
            'lead': SellerLeadSerializer(lead).data,
            'qualification': qual,
        }, status=status.HTTP_201_CREATED)


# ─── CH2 — Application (mixed: seller + reviewer) ────────────────

class ApplicationListCreateView(generics.ListCreateAPIView):
    """GET — list applications for the requesting user (or all, for
    staff).  POST — open a new draft."""
    serializer_class = SellerApplicationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = SellerApplication.objects.all().order_by('-created_at')
        user = self.request.user
        if not getattr(user, 'is_staff', False):
            qs = qs.filter(applicant_email__iexact=user.email)
        return qs

    def perform_create(self, serializer):
        app = serializer.save(applicant=self.request.user,
                              applicant_email=self.request.user.email)
        SellerOnboardingEvent.log(
            application=app, actor=self.request.user,
            kind='application.draft_created',
            payload={'company_name': app.company_name},
        )


class ApplicationSubmitView(APIView):
    """POST /applications/<id>/submit — run eligibility gate +
    transition to submitted (or rejected on hard failure)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        app = get_object_or_404(SellerApplication, pk=pk)
        if app.applicant_email.lower() != request.user.email.lower() \
           and not request.user.is_staff:
            return Response({'detail': 'Not your application.'}, status=403)
        if app.status != 'draft':
            return Response({'detail': 'Already submitted.'}, status=409)
        result = services.check_eligibility(app)
        if not result['eligible']:
            # The doc's CH2.3 rejects on eligibility fail. We move
            # straight to 'rejected' so the funnel report shows the
            # drop-off accurately.
            try:
                app.apply_transition('submitted', actor=request.user)
                app.apply_transition('rejected', actor=request.user,
                                     notes=result['code'])
            except Exception:
                pass
            return Response({'eligible': False, **result}, status=422)
        app.apply_transition('submitted', actor=request.user,
                             notes='eligibility passed')
        # Auto-advance to kyc_pending — the next step is doc upload.
        app.apply_transition('kyc_pending', actor=request.user)
        return Response({'eligible': True,
                         'application': SellerApplicationSerializer(app).data})


# ─── CH3 — KYC document upload ───────────────────────────────────

class KycDocumentUploadView(generics.CreateAPIView):
    """POST /applications/<id>/kyc-documents — register a uploaded doc.

    For dev we accept `file_key` directly (S3 key from a pre-signed
    upload).  Production wires a real storage adapter behind the
    scenes; the model is the same."""
    serializer_class = KycDocumentSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        app = get_object_or_404(SellerApplication, pk=kwargs.get('pk'))
        if app.applicant_email.lower() != request.user.email.lower():
            return Response({'detail': 'Not your application.'}, status=403)
        data = dict(request.data)
        data['application'] = str(app.id)
        s = self.get_serializer(data=data)
        s.is_valid(raise_exception=True)
        doc = s.save(application=app)
        SellerOnboardingEvent.log(
            application=app, actor=request.user,
            kind='kyc.document_uploaded',
            payload={'doc_id': str(doc.id), 'type': doc.document_type},
        )
        # Auto-move to kyc_review once required docs are present.
        if app.status == 'kyc_pending':
            try:
                app.apply_transition('kyc_review')
            except Exception:
                pass
        # Auto-approve check — when OCR confidence is high enough,
        # skip the manual queue. For dev/no-OCR, this is a no-op
        # because confidence defaults to 0.
        kyc = services.evaluate_kyc(app)
        if kyc.get('auto_approve'):
            app.apply_transition('kyc_approved', notes='auto-approve threshold')
        return Response(KycDocumentSerializer(doc).data, status=201)


# ─── Admin KYC decision ──────────────────────────────────────────

class AdminKycDecisionView(APIView):
    """POST /admin/applications/<id>/kyc-decide  body:
    {decision: approved|rejected|request_more, kyc_score, notes,
     rejection_codes, required_additional_docs}"""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        app = get_object_or_404(SellerApplication, pk=pk)
        decision = request.data.get('decision')
        notes = request.data.get('notes', '')
        score = int(request.data.get('kyc_score') or 0)
        codes = request.data.get('rejection_codes') or []

        app.reviewer = request.user
        if decision == 'approved':
            app.kyc_score = score
            app.save(update_fields=['reviewer', 'kyc_score'])
            app.apply_transition('kyc_approved', actor=request.user,
                                 notes=notes)
            return Response({'detail': 'KYC approved.'})
        if decision == 'rejected':
            app.rejection_reason = (notes or '')[:500]
            app.rejection_codes = codes
            app.save(update_fields=['reviewer', 'rejection_reason', 'rejection_codes'])
            # kyc_review → kyc_rejected → rejected (final).
            app.apply_transition('kyc_rejected', actor=request.user, notes=notes)
            app.apply_transition('rejected', actor=request.user)
            return Response({'detail': 'KYC rejected.'})
        if decision == 'request_more':
            app.save(update_fields=['reviewer'])
            app.apply_transition('more_info', actor=request.user, notes=notes)
            return Response({'detail': 'More info requested.'})
        return Response({'detail': 'invalid decision'}, status=400)


# ─── CH4 — Agreement ─────────────────────────────────────────────

class AgreementForApplicationView(APIView):
    """GET /applications/<id>/agreement — the current pending or
    signed agreement. Returns 404 if no template has been generated
    (KYC not yet approved)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        app = get_object_or_404(SellerApplication, pk=pk)
        if app.applicant_email.lower() != request.user.email.lower() \
           and not request.user.is_staff:
            return Response({'detail': 'forbidden'}, status=403)
        ag = app.agreements.order_by('-created_at').first()
        if ag is None:
            return Response({'detail': 'no agreement yet'}, status=404)
        return Response({
            **SellerAgreementSerializer(ag).data,
            'body': ag.body_personalised,
        })


class AgreementSignView(APIView):
    """POST /agreements/<token>/sign — the signing endpoint named in
    CH4.2. Accepts the token from the email link so the seller can
    sign without being logged into MICHA (email = identity)."""
    permission_classes = [AllowAny]

    def post(self, request, token):
        ag = get_object_or_404(SellerAgreement, signing_token=token)
        try:
            result = services.sign_agreement(
                agreement=ag,
                signature_name=request.data.get('signature_name', ''),
                ip=request.META.get('REMOTE_ADDR', ''),
                ua=request.META.get('HTTP_USER_AGENT', ''),
                scroll_pct=int(request.data.get('scroll_completion_pct') or 0),
                checkbox_confirmed=bool(request.data.get('checkbox_confirmed')),
            )
        except ValueError as e:
            return Response({'code': str(e)}, status=422)
        return Response(result)


# ─── CH5.2 — Fee invoice ────────────────────────────────────────

class FeeInvoicePayView(APIView):
    """POST /fee-invoices/<id>/mark-paid — simulator endpoint. In
    production the Alipay/PSP webhook calls this. Body:
    {payment_reference}."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        inv = get_object_or_404(SellerFeeInvoice, pk=pk)
        if inv.application.applicant_email.lower() != request.user.email.lower() \
           and not request.user.is_staff:
            return Response({'detail': 'forbidden'}, status=403)
        if inv.status == 'paid':
            return Response({'detail': 'already paid'}, status=409)
        inv.status = 'paid'
        inv.paid_at = timezone.now()
        inv.paid_amount = inv.final_amount
        inv.payment_reference = (request.data.get('payment_reference') or '')[:120]
        inv.save(update_fields=[
            'status', 'paid_at', 'paid_amount', 'payment_reference',
        ])
        SellerOnboardingEvent.log(
            application=inv.application, actor=request.user,
            kind='fee_invoice.paid',
            payload={'invoice_id': str(inv.id), 'amount': str(inv.final_amount)},
        )
        try:
            inv.application.apply_transition('fee_paid', actor=request.user)
        except Exception:
            pass
        return Response({'detail': 'paid', 'invoice': SellerFeeInvoiceSerializer(inv).data})


# ─── CH7.1 — Getting Started Wizard status ───────────────────────

class WizardStatusView(APIView):
    """GET /seller-onboarding/wizard — returns the 6-step Getting
    Started checklist. Pulls from SellerOnboardingChecklist if it
    exists (the legacy 7-field model), otherwise derives from the
    seller's state."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        # Try the legacy checklist first.
        try:
            from apps.seller.models import SellerOnboardingChecklist
            cl = SellerOnboardingChecklist.objects.filter(seller=user).first()
        except Exception:
            cl = None

        steps = [
            {'id': 1, 'title': 'Store Profile',
             'done': bool(cl and cl.profile_completed)},
            {'id': 2, 'title': 'Shipping Templates',
             'done': self._has_shipping_template(user)},
            {'id': 3, 'title': 'Category Enrolment',
             'done': self._has_enrolment(user)},
            {'id': 4, 'title': 'First Product Listing',
             'done': bool(cl and cl.first_product_added)},
            {'id': 5, 'title': 'Payout Settings',
             'done': bool(cl and cl.bank_account_added)},
            {'id': 6, 'title': 'Launch Promotion',
             'done': False},  # promotion stub — not tracked yet
        ]
        completed = sum(1 for s in steps if s['done'])
        return Response({
            'completed': completed, 'total': len(steps),
            'percentage': round(completed * 100 / len(steps)),
            'steps': steps,
        })

    def _has_shipping_template(self, user):
        try:
            from apps.shipping.models import ShippingTemplate
            return ShippingTemplate.objects.filter(seller=user).exists()
        except Exception:
            return False

    def _has_enrolment(self, user):
        return SellerCategoryEnrolment.objects.filter(
            seller=user, status='approved').exists()


# ─── CH8 — Training & certificates ───────────────────────────────

class TrainingProgressView(APIView):
    """GET /training/progress — list all modules with seller's state.
    POST body {module_id, progress_pct, quiz_score} updates."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = list(SellerTrainingProgress.objects.filter(seller=request.user))
        return Response({
            'progress': SellerTrainingProgressSerializer(rows, many=True).data,
            'certificates': SellerCertificateSerializer(
                SellerCertificate.objects.filter(seller=request.user), many=True,
            ).data,
        })

    def post(self, request):
        module_id = request.data.get('module_id')
        if module_id not in dict(
            __import__('apps.seller_onboarding.models', fromlist=['TRAINING_MODULE_CHOICES']).TRAINING_MODULE_CHOICES,
        ):
            return Response({'detail': 'invalid module'}, status=400)
        row, _ = SellerTrainingProgress.objects.get_or_create(
            seller=request.user, module_id=module_id,
            defaults={'started_at': timezone.now()},
        )
        new_pct = request.data.get('progress_pct')
        if new_pct is not None:
            row.progress_pct = max(0, min(100, int(new_pct)))
            if row.progress_pct > 0 and not row.started_at:
                row.started_at = timezone.now()
            if row.progress_pct == 100:
                row.status = 'completed'
        score = request.data.get('quiz_score')
        if score is not None:
            row.quiz_attempts += 1
            row.quiz_score = max(row.quiz_score, int(score))
            row.passed = row.quiz_score >= 80
            if row.passed:
                row.status = 'completed'
                row.completed_at = timezone.now()
        row.save()
        # Issue certificate on first pass.
        cert = None
        if row.passed and not SellerCertificate.objects.filter(
            seller=request.user, module_id=module_id,
        ).exists():
            import hashlib
            payload = f'{request.user.pk}|{module_id}|{timezone.now().isoformat()}'
            cert = SellerCertificate.objects.create(
                seller=request.user, module_id=module_id,
                certificate_type=f'{module_id}_certificate',
                certificate_hash=hashlib.sha256(payload.encode()).hexdigest(),
                verification_url=f'/verify-certificate/{module_id}/',
            )
            SellerOnboardingEvent.log(
                seller=request.user, kind='training.certificate_issued',
                payload={'module': module_id, 'cert_id': str(cert.id)},
            )
        return Response({
            'progress': SellerTrainingProgressSerializer(row).data,
            'certificate': SellerCertificateSerializer(cert).data if cert else None,
        })


# ─── CH10 — Category enrolment ───────────────────────────────────

class CategoryEnrolmentView(generics.ListCreateAPIView):
    serializer_class = SellerCategoryEnrolmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SellerCategoryEnrolment.objects.filter(seller=self.request.user)

    def create(self, request, *args, **kwargs):
        category_id = request.data.get('category_id')
        enrolment_type = request.data.get('enrolment_type', 'open')
        documents = request.data.get('documents_submitted') or []
        result = services.enrol_category(
            seller=request.user, category_id=category_id,
            enrolment_type=enrolment_type, documents=documents,
        )
        if not result['ok']:
            return Response(result, status=403)
        obj = SellerCategoryEnrolment.objects.get(pk=result['enrolment_id'])
        return Response(SellerCategoryEnrolmentSerializer(obj).data, status=201)


# ─── CH11 — Category upgrade ─────────────────────────────────────

class CategoryUpgradeRequestView(generics.ListCreateAPIView):
    serializer_class = SellerCategoryUpgradeRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SellerCategoryUpgradeRequest.objects.filter(seller=self.request.user)

    def perform_create(self, serializer):
        # CH11.1 auto-eligibility — tenure + dispute rate + feedback.
        user = self.request.user
        tier = SellerTierState.objects.filter(seller=user).first()
        metrics = services.get_seller_metrics(user)
        if metrics['dispute_rate'] > 0.05:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'code': 'DISPUTE_RATE_TOO_HIGH',
                                   'current': metrics['dispute_rate'],
                                   'max': 0.05})
        if metrics['feedback_score'] < 0.90:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'code': 'FEEDBACK_TOO_LOW',
                                   'current': metrics['feedback_score'],
                                   'min': 0.90})
        upgrade = serializer.save(
            seller=user,
            metrics_snapshot=metrics,
        )
        SellerOnboardingEvent.log(
            seller=user, kind='category_upgrade.requested',
            payload={'upgrade_id': upgrade.pk,
                     'from': upgrade.current_category_id,
                     'to': upgrade.target_category_id},
        )


# ─── CH12 — Brand registration ──────────────────────────────────

class SellerBrandView(generics.ListCreateAPIView):
    serializer_class = SellerBrandSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SellerBrand.objects.filter(seller=self.request.user)

    def perform_create(self, serializer):
        brand = serializer.save(seller=self.request.user)
        SellerOnboardingEvent.log(
            seller=self.request.user, kind='brand.registration_requested',
            payload={'brand_id': str(brand.id), 'brand_name': brand.brand_name},
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_name_check(request):
    """POST /brands/check  body: {brand_name} — returns availability +
    conflicts. Stub for the WIPO integration; today we just check our
    own DB for exact-name collisions."""
    name = (request.data.get('brand_name') or '').strip()
    if not name:
        return Response({'detail': 'brand_name required'}, status=400)
    conflicts = list(SellerBrand.objects.filter(
        brand_name__iexact=name,
    ).values('id', 'brand_name', 'brand_type', 'status'))
    return Response({
        'available': len(conflicts) == 0,
        'conflicts': conflicts,
        'recommendation': 'Available — proceed with registration.'
            if not conflicts else
            'Name in use; pick a different brand name or prove ownership.',
    })


# ─── CH14 — Tier ─────────────────────────────────────────────────

class MyTierView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        state, _ = SellerTierState.objects.get_or_create(seller=request.user)
        recent = SellerTierHistory.objects.filter(
            seller=request.user)[:10]
        return Response({
            'state': SellerTierStateSerializer(state).data,
            'history': SellerTierHistorySerializer(recent, many=True).data,
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def recalculate_tier_now(request):
    """POST /tier/recalculate-now — admin override or seller-on-demand
    recalculation (rate-limited at the gateway in prod)."""
    return Response(services.recalculate_tier(request.user))


# ─── CH16 — Health score ─────────────────────────────────────────

class MyHealthScoreView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        latest = SellerHealthScore.objects.filter(
            seller=request.user).order_by('-snapshot_date').first()
        trend = SellerHealthScore.objects.filter(
            seller=request.user,
            snapshot_date__gte=timezone.now().date() - timedelta(days=30),
        ).order_by('snapshot_date')
        if not latest:
            services.snapshot_health_score(request.user)
            latest = SellerHealthScore.objects.filter(
                seller=request.user).order_by('-snapshot_date').first()
        return Response({
            'latest': SellerHealthScoreSerializer(latest).data if latest else None,
            'trend': SellerHealthScoreSerializer(trend, many=True).data,
        })


# ─── CH18 — Holiday mode ─────────────────────────────────────────

class HolidayModeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from datetime import date
        try:
            start = date.fromisoformat(request.data.get('start_date'))
            end = date.fromisoformat(request.data.get('end_date'))
        except Exception:
            return Response({'detail': 'invalid dates'}, status=400)
        check = services.can_activate_holiday(request.user, start_date=start, end_date=end)
        if not check['ok']:
            return Response(check, status=422)
        log = SellerHolidayLog.objects.create(
            seller=request.user, start_date=start, end_date=end,
            reason=request.data.get('reason', '')[:255],
            message_to_buyers=request.data.get('message_to_buyers', ''),
        )
        SellerOnboardingEvent.log(
            seller=request.user, kind='holiday.activated',
            payload={'log_id': log.pk, 'start': start.isoformat(),
                     'end': end.isoformat()},
        )
        return Response(SellerHolidayLogSerializer(log).data, status=201)

    def delete(self, request):
        log = SellerHolidayLog.objects.filter(
            seller=request.user, deactivated_at__isnull=True,
        ).order_by('-activated_at').first()
        if not log:
            return Response({'detail': 'not on holiday'}, status=404)
        log.deactivated_at = timezone.now()
        log.early_deactivated = True
        log.save(update_fields=['deactivated_at', 'early_deactivated'])
        SellerOnboardingEvent.log(
            seller=request.user, kind='holiday.deactivated_early',
            payload={'log_id': log.pk},
        )
        return Response(SellerHolidayLogSerializer(log).data)


# ─── CH20 — Reactivation ─────────────────────────────────────────

class ReactivationRequestView(generics.ListCreateAPIView):
    serializer_class = SellerReactivationRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SellerReactivationRequest.objects.filter(seller=self.request.user)

    def perform_create(self, serializer):
        obj = serializer.save(seller=self.request.user)
        SellerOnboardingEvent.log(
            seller=self.request.user,
            kind='reactivation.requested',
            payload={'request_id': obj.pk, 'reason': obj.suspension_reason},
        )


# ─── Admin observability ─────────────────────────────────────────

class AdminApplicationQueueView(generics.ListAPIView):
    """GET /admin/applications/queue?status=kyc_review — review queue."""
    serializer_class = SellerApplicationSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = SellerApplication.objects.all().order_by('submitted_at')
        wanted = self.request.query_params.get('status')
        if wanted:
            qs = qs.filter(status=wanted)
        return qs


class ApplicationEventsView(generics.ListAPIView):
    """GET /applications/<id>/events — the audit timeline."""
    serializer_class = SellerOnboardingEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        app_id = self.kwargs['pk']
        qs = SellerOnboardingEvent.objects.filter(application_id=app_id)
        if not getattr(self.request.user, 'is_staff', False):
            # Restrict to events the requesting seller owns.
            qs = qs.filter(application__applicant_email__iexact=self.request.user.email)
        return qs
