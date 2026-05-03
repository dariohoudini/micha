
PROHIBITED_KEYWORDS = [
    'firearm', 'gun', 'pistol', 'rifle', 'ammunition', 'bullet', 'weapon',
    'alcohol', 'beer', 'wine', 'whisky', 'vodka', 'spirits',
    'tobacco', 'cigarette', 'vaping', 'e-cigarette',
    'counterfeit', 'fake', 'replica', 'imitation',
    'cocaine', 'heroin', 'cannabis', 'marijuana', 'drug', 'narcotic',
    'pornograph', 'adult content', 'explicit',
    'explosive', 'hazardous', 'toxic chemical',
]

def validate_listing_content(value):
    from django.core.exceptions import ValidationError
    lower = value.lower()
    for keyword in PROHIBITED_KEYWORDS:
        if keyword in lower:
            raise ValidationError(
                f'This listing contains prohibited content ({keyword}). '
                'Please review Section 8 of our Terms and Conditions.'
            )

from django.db import models
from django.conf import settings
import uuid

User = settings.AUTH_USER_MODEL


class Listing(models.Model):
    """
    A general listing posted by any authenticated user.
    Simpler than a Product (no store required).
    """
    SALE_TYPE_CHOICES = (
        ('sale', 'For Sale'),
        ('rent', 'For Rent'),
        ('free', 'Free / Give Away'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
    title = models.CharField(max_length=255, validators=[validate_listing_content])
    description = models.TextField(blank=True, validators=[validate_listing_content])
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sale_type = models.CharField(max_length=10, choices=SALE_TYPE_CHOICES, default='sale')
    city = models.CharField(max_length=100, blank=True, null=True)
    neighbourhood = models.CharField(max_length=100, blank=True, null=True)
    street = models.CharField(max_length=200, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address_hash = models.CharField(max_length=64, blank=True, db_index=True)
    is_duplicate = models.BooleanField(default=False)
    duplicate_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='duplicates')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def compute_address_hash(self):
        import hashlib
        parts = [
            (self.street or '').lower().strip(),
            (self.neighbourhood or '').lower().strip(),
            (self.city or '').lower().strip(),
            (self.province or '').lower().strip(),
        ]
        raw = '|'.join(p for p in parts if p)
        if not raw:
            return ''
        return hashlib.sha256(raw.encode()).hexdigest()[:64]

    def check_duplicate(self):
        """Returns existing listing if this is a duplicate, else None."""
        # Check by address hash
        if self.address_hash:
            existing = Listing.objects.filter(
                address_hash=self.address_hash,
                sale_type=self.sale_type,
                is_active=True,
            ).exclude(pk=self.pk).first()
            if existing:
                return existing
        return None

    def save(self, *args, **kwargs):
        self.address_hash = self.compute_address_hash()
        if self._state.adding:
            duplicate = self.check_duplicate()
            if duplicate:
                self.is_duplicate = True
                self.duplicate_of = duplicate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ListingImage(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='listings/images/')
    image_hash = models.CharField(max_length=64, blank=True, db_index=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def compute_hash(image_file):
        try:
            import imagehash
            from PIL import Image
            img = Image.open(image_file)
            return str(imagehash.phash(img))
        except Exception:
            return ''

    def save(self, *args, **kwargs):
        self.address_hash = self.compute_address_hash()
        if self._state.adding:
            duplicate = self.check_duplicate()
            if duplicate:
                self.is_duplicate = True
                self.duplicate_of = duplicate
        super().save(*args, **kwargs)
