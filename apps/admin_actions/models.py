from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class AdminActionLog(models.Model):
    """Immutable audit trail of every admin action."""
    ACTION_TYPES = (
        ('suspend_user', 'Suspend User'),
        ('ban_user', 'Ban User'),
        ('activate_user', 'Activate User'),
        ('approve_verification', 'Approve Verification'),
        ('reject_verification', 'Reject Verification'),
        ('approve_payout', 'Approve Payout'),
        ('reject_payout', 'Reject Payout'),
        ('resolve_dispute_buyer', 'Resolve Dispute (Buyer)'),
        ('resolve_dispute_seller', 'Resolve Dispute (Seller)'),
        ('remove_product', 'Remove Product'),
        ('feature_product', 'Feature Product'),
        ('set_commission', 'Set Commission Rate'),
        ('issue_refund', 'Issue Refund'),
        ('create_announcement', 'Create Announcement'),
        ('assign_role', 'Assign Role'),
        ('revoke_role', 'Revoke Role'),
        ('view_encrypted_data', 'View Encrypted Data'),
    )

    admin = models.ForeignKey(User, on_delete=models.PROTECT, related_name='admin_actions_taken')
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    target_type = models.CharField(max_length=50)
    target_id = models.CharField(max_length=100)
    target_repr = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['admin', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['target_type', 'target_id']),
        ]

    @classmethod
    def log(cls, request, action, target, note='', metadata=None):
        ip = ''
        ua = ''
        if request:
            xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
            ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')
            ua = request.META.get('HTTP_USER_AGENT', '')[:200]
        target_repr = getattr(target, 'email', None) or getattr(target, 'title', None) or str(target)[:200]
        return cls.objects.create(
            admin=request.user, action=action,
            target_type=type(target).__name__.lower(),
            target_id=str(getattr(target, 'pk', '')),
            target_repr=target_repr, note=note,
            ip_address=ip or None, user_agent=ua,
            metadata=metadata or {},
        )

    def __str__(self):
        return f"{self.admin.email} → {self.action} on {self.target_type}:{self.target_id}"


class AdminAction(models.Model):
    """Legacy alias — kept for backwards compatibility with old views."""
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='old_admin_actions')
    action = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.admin.email}: {self.action}"


class ProductModeration(models.Model):
    """Track product moderation decisions."""
    STATUS = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    )
    product = models.OneToOneField(
        'products.Product', on_delete=models.CASCADE, related_name='moderation'
    )
    status = models.CharField(max_length=10, choices=STATUS, default='pending')
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='moderated_products'
    )
    rejection_reason = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', '-created_at'])]

    def __str__(self):
        return f"Moderation({self.product.title}): {self.status}"
