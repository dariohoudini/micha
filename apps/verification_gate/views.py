"""
apps/verification_gate/views.py
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from django.db.models import Q


class VerificationStatusView(APIView):
    """
    GET /api/verification-gate/status/
    Returns current verification status for the authenticated seller.
    Frontend polls this to know which screen to show.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            v = request.user.seller_verification
            return Response({
                'status': v.status,
                'is_active': v.is_active,
                'lock_reason': v.lock_reason if not v.is_active else None,
                'rejection_reason': v.rejection_reason if v.status == 'rejected' else None,
                'rejection_notes': v.rejection_notes if v.status == 'rejected' else None,
                'bi_expiry_date': v.bi_expiry_date,
                'days_until_bi_expiry': v.days_until_bi_expiry,
                'next_selfie_due': v.next_selfie_due,
                'days_until_selfie_due': v.days_until_selfie_due,
                'submitted_at': v.first_submitted_at,
                'approved_at': v.approved_at,
                'full_name': v.full_name if v.is_active else None,
            })
        except Exception:
            return Response({
                'status': 'not_submitted',
                'is_active': False,
                'lock_reason': None,
            })


class SubmitVerificationView(APIView):
    """
    POST /api/verification-gate/submit/
    Seller submits BI front, back, selfie and ID details.
    Multipart form data.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        from .models import SellerVerification, VerificationAuditLog

        # Validate required fields
        required_fields = ['full_name', 'bi_number', 'date_of_birth', 'bi_expiry_date']
        missing = [f for f in required_fields if not request.data.get(f)]
        if missing:
            return Response({'error': f'Campos obrigatórios em falta: {", ".join(missing)}'}, status=400)

        required_files = ['bi_front_photo', 'bi_back_photo', 'initial_selfie']
        missing_files = [f for f in required_files if f not in request.FILES]
        if missing_files:
            return Response({'error': f'Fotos obrigatórias em falta: {", ".join(missing_files)}'}, status=400)

        # Get or create verification record
        v, created = SellerVerification.objects.get_or_create(seller=request.user)

        # Don't allow resubmission if already approved and active
        if v.is_active and v.status == 'approved':
            return Response({'error': 'Verificação já aprovada.'}, status=400)

        # Update record
        v.full_name = request.data.get('full_name', '').strip()
        v.bi_number = request.data.get('bi_number', '').strip().upper()
        v.date_of_birth = request.data.get('date_of_birth')
        v.place_of_birth = request.data.get('place_of_birth', '').strip()
        v.issuing_province = request.data.get('issuing_province', '')
        v.bi_issue_date = request.data.get('bi_issue_date') or None
        v.bi_expiry_date = request.data.get('bi_expiry_date')
        v.bi_front_photo = request.FILES['bi_front_photo']
        v.bi_back_photo = request.FILES['bi_back_photo']
        v.initial_selfie = request.FILES['initial_selfie']
        v.status = 'pending'
        v.is_active = False
        v.rejection_reason = ''
        v.rejection_notes = ''
        v.submission_count += 1

        if not v.first_submitted_at:
            v.first_submitted_at = timezone.now()

        v.save()

        # Audit log
        VerificationAuditLog.objects.create(
            verification=v,
            action='submitted',
            performed_by=request.user,
            details={
                'bi_number': v.bi_number,
                'submission_count': v.submission_count,
            }
        )

        # Notify admins
        from .tasks import notify_admin_new_submission
        notify_admin_new_submission.delay(str(v.id))

        return Response({
            'status': 'pending',
            'message': 'Verificação submetida com sucesso. Aguarde a análise do administrador.',
            'submission_count': v.submission_count,
        })


class SubmitMonthlySelfieView(APIView):
    """
    POST /api/verification-gate/monthly-selfie/
    Seller submits monthly renewal selfie.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        from .models import SellerVerification, MonthlySelfie

        try:
            v = request.user.seller_verification
        except SellerVerification.DoesNotExist:
            return Response({'error': 'Verificação inicial não encontrada.'}, status=404)

        if v.status not in ('approved', 'locked'):
            return Response({'error': 'Verificação inicial ainda não aprovada.'}, status=400)

        if 'selfie' not in request.FILES:
            return Response({'error': 'Foto selfie obrigatória.'}, status=400)

        selfie = MonthlySelfie.objects.create(
            verification=v,
            selfie=request.FILES['selfie'],
            status='pending',
        )

        # Notify admins
        from .tasks import notify_admin_monthly_selfie
        notify_admin_monthly_selfie.delay(str(selfie.id))

        return Response({
            'status': 'pending',
            'message': 'Selfie submetida. Aguarde aprovação do administrador.',
            'selfie_id': str(selfie.id),
        })


# ── Admin views ───────────────────────────────────────────────────────────────

class AdminVerificationListView(APIView):
    """
    GET /api/verification-gate/admin/list/?status=pending
    Lists all verification submissions for admin review.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        from .models import SellerVerification

        status = request.query_params.get('status', 'pending')
        qs = SellerVerification.objects.select_related('seller').order_by('-updated_at')

        if status != 'all':
            qs = qs.filter(status=status)

        search = request.query_params.get('search', '')
        if search:
            qs = qs.filter(
                Q(seller__email__icontains=search) |
                Q(full_name__icontains=search) |
                Q(bi_number__icontains=search)
            )

        page = int(request.query_params.get('page', 1))
        per_page = 20
        total = qs.count()
        items = qs[(page-1)*per_page:page*per_page]

        data = []
        for v in items:
            data.append({
                'id': str(v.id),
                'seller_id': str(v.seller.id),
                'seller_email': v.seller.email,
                'full_name': v.full_name,
                'bi_number': v.bi_number,
                'bi_expiry_date': v.bi_expiry_date,
                'status': v.status,
                'submission_count': v.submission_count,
                'submitted_at': v.first_submitted_at,
                'bi_front_photo': request.build_absolute_uri(v.bi_front_photo.url) if v.bi_front_photo else None,
                'bi_back_photo': request.build_absolute_uri(v.bi_back_photo.url) if v.bi_back_photo else None,
                'initial_selfie': request.build_absolute_uri(v.initial_selfie.url) if v.initial_selfie else None,
                'rejection_reason': v.rejection_reason,
                'days_until_bi_expiry': v.days_until_bi_expiry,
            })

        return Response({
            'results': data,
            'total': total,
            'pending_count': SellerVerification.objects.filter(status='pending').count(),
        })


class AdminVerificationActionView(APIView):
    """
    POST /api/verification-gate/admin/<id>/action/
    Admin approves or rejects a verification.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, verification_id):
        from .models import SellerVerification, VerificationAuditLog

        try:
            v = SellerVerification.objects.get(id=verification_id)
        except SellerVerification.DoesNotExist:
            return Response({'error': 'Verificação não encontrada.'}, status=404)

        action = request.data.get('action')

        if action == 'approve':
            v.approve(reviewed_by=request.user)
            VerificationAuditLog.objects.create(
                verification=v,
                action='approved',
                performed_by=request.user,
            )
            return Response({'status': 'approved', 'message': f'{v.full_name} verificado com sucesso.'})

        elif action == 'reject':
            reason = request.data.get('reason', 'other')
            notes = request.data.get('notes', '')
            v.reject(reviewed_by=request.user, reason=reason, notes=notes)
            VerificationAuditLog.objects.create(
                verification=v,
                action='rejected',
                performed_by=request.user,
                details={'reason': reason, 'notes': notes},
            )
            return Response({'status': 'rejected'})

        return Response({'error': 'Acção inválida. Use approve ou reject.'}, status=400)


class AdminMonthlySelfieListView(APIView):
    """
    GET /api/verification-gate/admin/selfies/?status=pending
    Lists monthly selfie submissions for admin review.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        from .models import MonthlySelfie

        status = request.query_params.get('status', 'pending')
        qs = MonthlySelfie.objects.select_related(
            'verification__seller'
        ).order_by('-submitted_at')

        if status != 'all':
            qs = qs.filter(status=status)

        items = qs[:50]
        data = [{
            'id': str(s.id),
            'seller_email': s.verification.seller.email,
            'seller_name': s.verification.full_name,
            'selfie_url': request.build_absolute_uri(s.selfie.url) if s.selfie else None,
            'status': s.status,
            'submitted_at': s.submitted_at,
            'days_until_due': s.verification.days_until_selfie_due,
        } for s in items]

        return Response({
            'results': data,
            'pending_count': MonthlySelfie.objects.filter(status='pending').count(),
        })


class AdminMonthlySelfieActionView(APIView):
    """POST /api/verification-gate/admin/selfies/<id>/action/"""
    permission_classes = [IsAdminUser]

    def post(self, request, selfie_id):
        from .models import MonthlySelfie

        try:
            selfie = MonthlySelfie.objects.get(id=selfie_id)
        except MonthlySelfie.DoesNotExist:
            return Response({'error': 'Selfie não encontrada.'}, status=404)

        action = request.data.get('action')

        if action == 'approve':
            selfie.approve(reviewed_by=request.user)
            return Response({'status': 'approved'})

        elif action == 'reject':
            reason = request.data.get('reason', 'Selfie não aceite. Submeta novamente.')
            selfie.status = 'rejected'
            selfie.rejection_reason = reason
            selfie.reviewed_by = request.user
            selfie.reviewed_at = timezone.now()
            selfie.save()

            from .tasks import notify_selfie_rejected
            notify_selfie_rejected.delay(
                str(selfie.verification.seller.id), reason
            )
            return Response({'status': 'rejected'})

        return Response({'error': 'Acção inválida.'}, status=400)
