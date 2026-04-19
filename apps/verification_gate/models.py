"""
apps/verification_gate/models.py

MICHA Express Identity Verification — Sellers & Store Owners Only.

Flow:
1. Seller registers → verification gate appears immediately
2. Submits: front BI + back BI + oval selfie
3. Admin reviews in admin panel → approves or rejects with reason
4. Approved → full seller access
5. Rejected → seller resubmits with correction

Monthly renewal:
- 14 days before monthly anniversary → push alert
- 7 days before → second alert
- Miss date → immediate lock → only login + verification visible
- New selfie submitted → admin reviews → unlocked

ID expiry:
- Expiry date entered manually by seller
- 14 days before → alert
- Day of expiry → immediate account lock
- Seller submits new BI → admin reviews → unlocked

Angolan BI fields captured:
- Full name (must match account name)
- BI number
- Date of birth
- Expiry date
- Place of birth
- Issuing province
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import uuid


VERIFICATION_STATUS = [
    ('not_submitted', 'Não submetido'),
    ('pending',       'Em análise'),
    ('approved',      'Aprovado'),
    ('rejected',      'Rejeitado'),
    ('expired',       'Expirado'),
    ('locked',        'Bloqueado'),
]

REJECTION_REASONS = [
    ('image_unclear',    'Imagem ilegível — resubmita com melhor qualidade'),
    ('id_mismatch',      'Dados do BI não correspondem ao perfil'),
    ('id_expired',       'BI expirado — submeta BI válido'),
    ('fake_id',          'Documento não reconhecido como BI angolano válido'),
    ('selfie_mismatch',  'Selfie não corresponde à foto do BI'),
    ('incomplete',       'Documentos incompletos — frente e verso obrigatórios'),
    ('other',            'Outro motivo — ver notas do administrador'),
]

ANGOLA_PROVINCES = [
    ('Luanda', 'Luanda'), ('Benguela', 'Benguela'), ('Huambo', 'Huambo'),
    ('Huíla', 'Huíla'), ('Cabinda', 'Cabinda'), ('Uíge', 'Uíge'),
    ('Namibe', 'Namibe'), ('Malanje', 'Malanje'), ('Bié', 'Bié'),
    ('Moxico', 'Moxico'), ('Cunene', 'Cunene'), ('Cuando Cubango', 'Cuando Cubango'),
    ('Lunda Norte', 'Lunda Norte'), ('Lunda Sul', 'Lunda Sul'),
    ('Kwanza Norte', 'Kwanza Norte'), ('Kwanza Sul', 'Kwanza Sul'),
    ('Bengo', 'Bengo'), ('Zaire', 'Zaire'),
]


class SellerVerification(models.Model):
    """
    Master verification record per seller.
    One record per seller — updated on each submission cycle.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='seller_verification'
    )

    # ── Current status ────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20, choices=VERIFICATION_STATUS, default='not_submitted'
    )
    is_active = models.BooleanField(
        default=False,
        help_text="True only when status=approved AND not expired AND monthly selfie current"
    )

    # ── ID information (typed by seller, verified against BI photo) ───────────
    full_name = models.CharField(max_length=200, blank=True)
    bi_number = models.CharField(
        max_length=20, blank=True,
        help_text="Angolan BI number e.g. 004567823LA042"
    )
    date_of_birth = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=100, blank=True)
    issuing_province = models.CharField(
        max_length=50, choices=ANGOLA_PROVINCES, blank=True
    )
    bi_issue_date = models.DateField(null=True, blank=True)
    bi_expiry_date = models.DateField(
        null=True, blank=True,
        help_text="BI expiry date — account locks on this date"
    )

    # ── Document photos ───────────────────────────────────────────────────────
    bi_front_photo = models.ImageField(
        upload_to='verification/bi/front/',
        null=True, blank=True,
        help_text="Front side of Angolan BI"
    )
    bi_back_photo = models.ImageField(
        upload_to='verification/bi/back/',
        null=True, blank=True,
        help_text="Back side of Angolan BI"
    )
    initial_selfie = models.ImageField(
        upload_to='verification/selfies/initial/',
        null=True, blank=True,
        help_text="Oval-framed selfie taken during initial verification"
    )

    # ── Admin review ──────────────────────────────────────────────────────────
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='verifications_reviewed'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(
        max_length=50, choices=REJECTION_REASONS, blank=True
    )
    rejection_notes = models.TextField(
        blank=True,
        help_text="Admin's additional notes shown to seller"
    )
    submission_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="How many times seller has submitted — track repeated rejections"
    )

    # ── Monthly selfie tracking ───────────────────────────────────────────────
    last_selfie_date = models.DateField(
        null=True, blank=True,
        help_text="Date of most recent approved monthly selfie"
    )
    next_selfie_due = models.DateField(
        null=True, blank=True,
        help_text="Date by which next selfie must be submitted"
    )
    selfie_alert_14_sent = models.BooleanField(default=False)
    selfie_alert_7_sent = models.BooleanField(default=False)

    # ── BI expiry tracking ────────────────────────────────────────────────────
    bi_expiry_alert_14_sent = models.BooleanField(default=False)
    bi_expiry_alert_7_sent = models.BooleanField(default=False)

    # ── Timestamps ────────────────────────────────────────────────────────────
    first_submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    lock_reason = models.CharField(
        max_length=50,
        choices=[
            ('bi_expired',       'BI expirado'),
            ('selfie_overdue',   'Selfie mensal em falta'),
            ('admin_lock',       'Bloqueado pelo administrador'),
            ('resubmit_pending', 'Aguarda nova submissão'),
        ],
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seller_verifications'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['bi_expiry_date']),
            models.Index(fields=['next_selfie_due']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"Verification({self.seller.email}, {self.status})"

    @property
    def bi_is_expired(self):
        if not self.bi_expiry_date:
            return False
        return self.bi_expiry_date <= timezone.now().date()

    @property
    def selfie_is_overdue(self):
        if not self.next_selfie_due:
            return False
        return timezone.now().date() > self.next_selfie_due

    @property
    def days_until_selfie_due(self):
        if not self.next_selfie_due:
            return None
        delta = self.next_selfie_due - timezone.now().date()
        return delta.days

    @property
    def days_until_bi_expiry(self):
        if not self.bi_expiry_date:
            return None
        delta = self.bi_expiry_date - timezone.now().date()
        return delta.days

    def approve(self, reviewed_by):
        """Admin approves verification."""
        from django.utils import timezone as tz
        self.status = 'approved'
        self.is_active = True
        self.reviewed_by = reviewed_by
        self.reviewed_at = tz.now()
        self.approved_at = tz.now()
        self.locked_at = None
        self.lock_reason = ''

        # Set monthly selfie schedule
        today = tz.now().date()
        self.last_selfie_date = today
        self.next_selfie_due = today + timedelta(days=30)
        self.selfie_alert_14_sent = False
        self.selfie_alert_7_sent = False

        self.save()

        # Notify seller
        from .tasks import notify_verification_approved
        notify_verification_approved.delay(str(self.seller.id))

    def reject(self, reviewed_by, reason, notes=''):
        """Admin rejects verification."""
        from django.utils import timezone as tz
        self.status = 'rejected'
        self.is_active = False
        self.reviewed_by = reviewed_by
        self.reviewed_at = tz.now()
        self.rejection_reason = reason
        self.rejection_notes = notes
        self.save()

        from .tasks import notify_verification_rejected
        notify_verification_rejected.delay(str(self.seller.id), reason, notes)

    def lock(self, reason):
        """Lock seller account."""
        from django.utils import timezone as tz
        self.is_active = False
        self.status = 'locked'
        self.lock_reason = reason
        self.locked_at = tz.now()
        self.save()

    def check_and_lock_if_needed(self):
        """
        Called daily by Celery. Locks account if BI expired or selfie overdue.
        """
        if not self.is_active:
            return

        if self.bi_is_expired:
            self.lock('bi_expired')
            from .tasks import notify_account_locked
            notify_account_locked.delay(str(self.seller.id), 'bi_expired')

        elif self.selfie_is_overdue:
            self.lock('selfie_overdue')
            from .tasks import notify_account_locked
            notify_account_locked.delay(str(self.seller.id), 'selfie_overdue')


class MonthlySelfie(models.Model):
    """
    Monthly selfie submissions.
    Each submission is reviewed by admin.
    Approved selfie resets the monthly clock.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    verification = models.ForeignKey(
        SellerVerification,
        on_delete=models.CASCADE,
        related_name='monthly_selfies'
    )
    selfie = models.ImageField(upload_to='verification/selfies/monthly/')
    status = models.CharField(
        max_length=20,
        choices=[('pending','Pendente'),('approved','Aprovado'),('rejected','Rejeitado')],
        default='pending'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='selfies_reviewed'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=200, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seller_monthly_selfies'
        ordering = ['-submitted_at']

    def approve(self, reviewed_by):
        """Approve selfie and reset monthly clock."""
        from django.utils import timezone as tz
        self.status = 'approved'
        self.reviewed_by = reviewed_by
        self.reviewed_at = tz.now()
        self.save()

        # Reset monthly clock on master verification
        today = tz.now().date()
        v = self.verification
        v.last_selfie_date = today
        v.next_selfie_due = today + timedelta(days=30)
        v.selfie_alert_14_sent = False
        v.selfie_alert_7_sent = False

        # Re-activate if was locked for selfie_overdue
        if v.lock_reason == 'selfie_overdue':
            v.status = 'approved'
            v.is_active = True
            v.locked_at = None
            v.lock_reason = ''

        v.save()

        from .tasks import notify_selfie_approved
        notify_selfie_approved.delay(str(v.seller.id))


class VerificationAuditLog(models.Model):
    """
    Audit trail of every verification action.
    Important for compliance and dispute resolution.
    """
    verification = models.ForeignKey(
        SellerVerification,
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=50)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'verification_audit_logs'
        ordering = ['-created_at']
