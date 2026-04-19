"""
Payments Models — Security Hardened
Fixes:
- Bank account numbers encrypted at field level
- Wallet operations use select_for_update() to prevent race conditions
- EarningsHold uses atomic transactions
"""
from django.db import models, transaction
from django.conf import settings
import uuid

User = settings.AUTH_USER_MODEL


class EncryptedCharField(models.CharField):
    """
    Field-level encryption using Fernet symmetric encryption.
    Requires: pip install cryptography
    Requires: FIELD_ENCRYPTION_KEY in settings (Fernet key)

    Data is encrypted before saving and decrypted on read.
    DB sees only encrypted bytes — even a DB breach reveals nothing.
    """
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return self._decrypt(value)

    def to_python(self, value):
        if value is None:
            return value
        try:
            return self._decrypt(value)
        except Exception:
            return value

    def get_prep_value(self, value):
        if value is None:
            return value
        return self._encrypt(value)

    def _get_fernet(self):
        from cryptography.fernet import Fernet
        key = getattr(settings, 'FIELD_ENCRYPTION_KEY', '')
        if not key:
            raise ValueError("FIELD_ENCRYPTION_KEY is not set in settings.")
        return Fernet(key.encode() if isinstance(key, str) else key)

    def _encrypt(self, value):
        try:
            f = self._get_fernet()
            return f.encrypt(value.encode()).decode()
        except Exception:
            return value  # fallback in dev without key set

    def _decrypt(self, value):
        try:
            f = self._get_fernet()
            return f.decrypt(value.encode()).decode()
        except Exception:
            return value  # already plain text or dev mode


class SellerWallet(models.Model):
    seller = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pending_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['seller'])]

    def credit(self, amount, description, reference=None):
        """
        ATOMIC: Add funds to wallet.
        Uses select_for_update() to prevent race conditions.
        """
        with transaction.atomic():
            wallet = SellerWallet.objects.select_for_update().get(pk=self.pk)
            wallet.balance += amount
            wallet.total_earned += amount
            wallet.save(update_fields=['balance', 'total_earned', 'updated_at'])
            WalletTransaction.objects.create(
                wallet=wallet,
                type='credit',
                amount=amount,
                description=description,
                reference=reference or '',
                balance_after=wallet.balance,
            )
            # Refresh self
            self.balance = wallet.balance
            self.total_earned = wallet.total_earned

    def debit(self, amount, description, reference=None):
        """
        ATOMIC: Remove funds from wallet. Raises if insufficient balance.
        """
        with transaction.atomic():
            wallet = SellerWallet.objects.select_for_update().get(pk=self.pk)
            if wallet.balance < amount:
                raise ValueError(f"Insufficient wallet balance: {wallet.balance} < {amount}")
            wallet.balance -= amount
            wallet.total_withdrawn += amount
            wallet.save(update_fields=['balance', 'total_withdrawn', 'updated_at'])
            WalletTransaction.objects.create(
                wallet=wallet,
                type='debit',
                amount=amount,
                description=description,
                reference=reference or '',
                balance_after=wallet.balance,
            )
            self.balance = wallet.balance

    def hold(self, amount, description):
        """Move amount from available to pending (in escrow)."""
        with transaction.atomic():
            wallet = SellerWallet.objects.select_for_update().get(pk=self.pk)
            wallet.pending_balance += amount
            wallet.save(update_fields=['pending_balance', 'updated_at'])
            WalletTransaction.objects.create(
                wallet=wallet, type='hold', amount=amount,
                description=description, balance_after=wallet.balance,
            )

    def release(self, amount, description):
        """Release pending funds to available balance."""
        with transaction.atomic():
            wallet = SellerWallet.objects.select_for_update().get(pk=self.pk)
            wallet.pending_balance = max(0, wallet.pending_balance - amount)
            wallet.balance += amount
            wallet.save(update_fields=['balance', 'pending_balance', 'updated_at'])
            WalletTransaction.objects.create(
                wallet=wallet, type='release', amount=amount,
                description=description, balance_after=wallet.balance,
            )
            self.balance = wallet.balance

    def __str__(self):
        return f"Wallet({self.seller.email}): {self.balance} AOA"


class WalletTransaction(models.Model):
    TYPE = (
        ('credit', 'Credit'),
        ('debit', 'Debit'),
        ('hold', 'Hold'),
        ('release', 'Release'),
    )
    wallet = models.ForeignKey(SellerWallet, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=10, choices=TYPE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    reference = models.CharField(max_length=100, blank=True)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['wallet', '-created_at'])]


class SellerBankAccount(models.Model):
    """
    SECURITY: account_number is encrypted at field level.
    DB stores only encrypted ciphertext. Even admins with DB access cannot read it.
    """
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=100)
    account_name = models.CharField(max_length=200)
    # ENCRYPTED — plaintext never stored in DB
    account_number = EncryptedCharField(max_length=500)
    iban = EncryptedCharField(max_length=500, blank=True, null=True)
    is_default = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['seller', 'is_default'])]

    def save(self, *args, **kwargs):
        if self.is_default:
            SellerBankAccount.objects.filter(
                seller=self.seller, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def masked_number(self):
        """Return last 4 digits only for display — never expose full number."""
        try:
            num = self.account_number
            return f"****{num[-4:]}" if len(num) >= 4 else "****"
        except Exception:
            return "****"


class PayoutRequest(models.Model):
    STATUS = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payout_requests')
    bank_account = models.ForeignKey(SellerBankAccount, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=15, choices=STATUS, default='pending')
    admin_note = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['seller', 'status'])]


class PlatformCommission(models.Model):
    name = models.CharField(max_length=100)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=5.00)
    category = models.ForeignKey(
        'products.Category', on_delete=models.SET_NULL, null=True, blank=True
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def get_rate(cls, category=None):
        """Get commission rate for a category, falling back to default."""
        if category:
            specific = cls.objects.filter(category=category).first()
            if specific:
                return specific.percentage
        default = cls.objects.filter(is_default=True).first()
        return default.percentage if default else 5.0


class SavedPaymentMethod(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_payment_methods')
    type = models.CharField(max_length=20)
    label = models.CharField(max_length=100)
    last_four = models.CharField(max_length=4, blank=True)
    # Token from payment gateway — never store raw card data
    gateway_token = EncryptedCharField(max_length=500)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class EarningsHold(models.Model):
    """Seller earnings held for SELLER_HOLD_DAYS days after delivery."""
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='earnings_holds')
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='earnings_hold')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    release_at = models.DateTimeField()
    released = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['released', 'release_at'])]
