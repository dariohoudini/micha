from django.db import models
from django.conf import settings
User = settings.AUTH_USER_MODEL

class SellerProfile(models.Model):
    seller = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seller_profile')
    store_logo = models.ImageField(upload_to='store_logos/', blank=True, null=True)
    store_banner = models.ImageField(upload_to='store_banners/', blank=True, null=True)
    return_policy = models.TextField(blank=True, null=True)
    shipping_policy = models.TextField(blank=True, null=True)
    working_hours = models.JSONField(default=dict)
    is_on_holiday = models.BooleanField(default=False)
    holiday_message = models.TextField(blank=True, null=True)
    holiday_until = models.DateField(null=True, blank=True)
    revenue_goal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    subscription_plan = models.CharField(max_length=20, choices=(('free','Free'),('premium','Premium')), default='free')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class SellerFAQ(models.Model):
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='faqs')
    question = models.CharField(max_length=300)
    answer = models.TextField()
    ordering = models.PositiveIntegerField(default=0)
    class Meta: ordering = ['ordering']

class SellerAnnouncement(models.Model):
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='announcements')
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']

class SellerOnboardingChecklist(models.Model):
    seller = models.OneToOneField(User, on_delete=models.CASCADE, related_name='onboarding')
    profile_completed = models.BooleanField(default=False)
    verification_submitted = models.BooleanField(default=False)
    verification_approved = models.BooleanField(default=False)
    first_store_created = models.BooleanField(default=False)
    first_product_added = models.BooleanField(default=False)
    bank_account_added = models.BooleanField(default=False)
    first_sale_made = models.BooleanField(default=False)
    @property
    def completion_percentage(self):
        f = [self.profile_completed, self.verification_submitted, self.verification_approved,
             self.first_store_created, self.first_product_added, self.bank_account_added, self.first_sale_made]
        return round(sum(f) / len(f) * 100)
