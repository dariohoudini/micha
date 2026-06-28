"""
MICHA Buyer Experience — deeper buyer-facing features.

Source: MICHA_Buyer_Experience_Deeper.docx (24 chapters). Builds the
genuinely-new buyer features; the rest already exist and are bridged.

Chapters HERE:
  CH2   OrderGiftOptions
  CH3   ProductSubscription
  CH4   ProductPriceHistory (immutable buyer-facing chart + anti-fake-discount)
  CH7   PrePurchaseQuestion (private, distinct from public products.ProductQA)
  CH8   BulkInquiry
  CH10  SavedComparison
  CH14  WishlistPriceWatch (price-drop; bridges apps.wishlist)
  CH18  AgeVerification, RestrictedCategory
  CH24  BuyerExperienceKpiSnapshot

Bridged (not duplicated):
  stock_engine.RestockSubscription (CH5) · search.RecentlyViewed (CH6/11) ·
  alerts.SavedSearch (CH15) · loyalty (CH17) · affiliates /
  buyer_engagement.ReferralActivation (CH19) ·
  buyer_engagement.RecoverySequenceState (CH20) · reviews (CH13) ·
  disputes (CH21) · notifications.NotificationPreference (CH22) ·
  last_mile.GpsDeliveryAddress (CH9) · accounting (loyalty redemption)
"""
import uuid

from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


# ──────────────────────────────────────────────────────────────────────
# CH2 — Gift options
# ──────────────────────────────────────────────────────────────────────

class OrderGiftOptions(models.Model):
    WRAP_CHOICES = [('none', 'Not wrapped'), ('basic', 'Basic wrap'),
                    ('premium', 'Premium wrap')]
    order_id = models.CharField(max_length=64, unique=True, db_index=True)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='gift_orders')
    is_gift = models.BooleanField(default=False)
    gift_message = models.CharField(max_length=300, blank=True)
    hide_price = models.BooleanField(default=True)
    gift_wrap = models.CharField(max_length=8, choices=WRAP_CHOICES,
                                 default='none')
    gift_wrap_fee_cents = models.IntegerField(default=0)
    gift_receipt_key = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH3 — Subscribe & Save
# ──────────────────────────────────────────────────────────────────────

class ProductSubscription(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('paused', 'Paused'),
                      ('cancelled', 'Cancelled')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          editable=False)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='subscriptions')
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True)
    seller = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                               blank=True, related_name='subscription_orders')
    quantity = models.PositiveIntegerField(default=1)
    frequency_days = models.PositiveIntegerField(default=30)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                       default=8)
    next_order_date = models.DateField(db_index=True)
    payment_method = models.CharField(max_length=24, default='wallet')  # prepaid
    delivery_address_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='active', db_index=True)
    total_orders = models.PositiveIntegerField(default=0)
    total_spent_cents = models.BigIntegerField(default=0)
    consecutive_failures = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'next_order_date'])]


# ──────────────────────────────────────────────────────────────────────
# CH4 — Price history (immutable, buyer-facing, anti-fake-discount)
# ──────────────────────────────────────────────────────────────────────

class ProductPriceHistory(models.Model):
    """INSERT-only buyer-facing price audit (doc CH4). Distinct from the
    internal pricing-engine history: this is the transparent 90-day chart
    and the anti-fake-discount source of truth.
    """
    REASON_CHOICES = [
        ('seller_update', 'Seller update'), ('promotion', 'Promotion'),
        ('flash_sale', 'Flash sale'), ('system_auto', 'System auto'),
        ('admin_override', 'Admin override'),
    ]
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True, db_index=True)
    price_cents = models.BigIntegerField()
    currency = models.CharField(max_length=3, default='AOA')
    change_reason = models.CharField(max_length=16, choices=REASON_CHOICES,
                                     default='seller_update')
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['product_id', '-recorded_at'])]


# ──────────────────────────────────────────────────────────────────────
# CH7 — Pre-purchase question (private)
# ──────────────────────────────────────────────────────────────────────

class PrePurchaseQuestion(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('answered', 'Answered'),
                      ('held', 'Held (moderation)'), ('expired', 'Expired')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          editable=False)
    product_id = models.CharField(max_length=64, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='pre_purchase_questions')
    buyer = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='asked_questions')
    question_text = models.TextField()
    attachment_key = models.CharField(max_length=300, blank=True)
    answer_text = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='pending', db_index=True)
    moderation_flag = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH8 — Bulk / wholesale inquiry
# ──────────────────────────────────────────────────────────────────────

class BulkInquiry(models.Model):
    PURPOSE_CHOICES = [
        ('resale', 'Resale'), ('personal', 'Personal'),
        ('business', 'Business'), ('institution', 'Institution'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('submitted', 'Submitted'), ('viewed', 'Viewed'), ('quoted', 'Quoted'),
        ('accepted', 'Accepted'), ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          editable=False)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='bulk_inquiries')
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='received_bulk_inquiries')
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True)
    quantity = models.PositiveIntegerField()
    delivery_province = models.CharField(max_length=40, blank=True)
    required_by_date = models.DateField(null=True, blank=True)
    purpose = models.CharField(max_length=12, choices=PURPOSE_CHOICES,
                               default='resale')
    buyer_message = models.TextField(blank=True)
    company_name = models.CharField(max_length=200, blank=True)
    nif = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='submitted', db_index=True)
    seller_quote_cents = models.IntegerField(null=True, blank=True)  # per unit
    seller_message = models.TextField(blank=True)
    order_id = models.CharField(max_length=64, blank=True)  # set on accept
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ──────────────────────────────────────────────────────────────────────
# CH10 — Saved comparison
# ──────────────────────────────────────────────────────────────────────

class SavedComparison(models.Model):
    buyer = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='saved_comparisons')
    name = models.CharField(max_length=120, blank=True)
    product_ids = models.JSONField(default=list)  # up to 4
    share_code = models.CharField(max_length=24, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH14 — Wishlist price-drop watch (bridges apps.wishlist)
# ──────────────────────────────────────────────────────────────────────

class WishlistPriceWatch(models.Model):
    buyer = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='price_watches')
    product_id = models.CharField(max_length=64, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True)
    price_at_add_cents = models.BigIntegerField()
    threshold_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                        default=5)
    alert_enabled = models.BooleanField(default=True)
    last_alerted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('buyer', 'product_id', 'sku_id')]


# ──────────────────────────────────────────────────────────────────────
# CH18 — Age verification
# ──────────────────────────────────────────────────────────────────────

class RestrictedCategory(models.Model):
    category_id = models.CharField(max_length=64, unique=True, db_index=True)
    category_name = models.CharField(max_length=120, blank=True)
    restriction_type = models.CharField(
        max_length=24,
        choices=[('alcohol', 'Alcohol'), ('tobacco', 'Tobacco'),
                 ('adult_health', 'Adult health'), ('gambling', 'Gambling'),
                 ('age_media', 'Age-restricted media')],
        default='alcohol')
    min_age = models.PositiveSmallIntegerField(default=18)
    requires_delivery_check = models.BooleanField(default=False)  # high-risk
    is_active = models.BooleanField(default=True)


class AgeVerification(models.Model):
    buyer = models.OneToOneField(User, on_delete=models.CASCADE,
                                 related_name='age_verification')
    age_verified = models.BooleanField(default=False)
    method = models.CharField(
        max_length=20,
        choices=[('self_declaration', 'Self-declaration'),
                 ('kyc_dob', 'KYC date of birth')],
        default='self_declaration')
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # 30-day cache


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ──────────────────────────────────────────────────────────────────────

class BuyerExperienceKpiSnapshot(models.Model):
    snapshot_date = models.DateField(unique=True)
    review_submission_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                default=0)   # >25
    review_photo_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                           default=0)        # >30
    subscribe_save_retention_pct = models.DecimalField(max_digits=5,
                                                       decimal_places=2,
                                                       default=0)  # >50
    loyalty_active_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                             default=0)      # >40
    address_book_adoption_pct = models.DecimalField(max_digits=5,
                                                    decimal_places=2,
                                                    default=0)  # >30
    referral_conversion_pct = models.DecimalField(max_digits=5,
                                                  decimal_places=2, default=0)
    active_subscriptions = models.IntegerField(default=0)
    pending_bulk_inquiries = models.IntegerField(default=0)
    pending_questions = models.IntegerField(default=0)
    computed_at = models.DateTimeField(auto_now=True)


class BuyerExperienceEvent(models.Model):
    kind = models.CharField(max_length=48, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='buyer_exp_events')
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @staticmethod
    def log(kind, actor=None, **payload):
        try:
            BuyerExperienceEvent.objects.create(
                kind=kind,
                actor=actor if getattr(actor, 'pk', None) else None,
                payload=payload)
        except Exception:
            pass
