"""
Products Models — Fixed
FIX 1: Product.save() no longer permanently blocks reactivation when stock is replenished.
FIX 2: created_by field added for multi-manager audit trail.
FIX 3: Manager.get_queryset() pre-fetches related to prevent N+1.
"""
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    icon = models.ImageField(upload_to='category_icons/', blank=True, null=True)
    image = models.ImageField(upload_to='category_images/', blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subcategories')
    is_custom = models.BooleanField(default=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='custom_categories')
    ordering = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('owner', 'name')
        ordering = ['ordering', 'name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['parent']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self): return self.name


class ProductTag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        indexes = [models.Index(fields=['name'])]

    def __str__(self): return self.name


class ActiveProductManager(models.Manager):
    """
    Manager with select_related pre-loaded.
    FIX: Using Product.active.all() avoids N+1 queries.
    Every query automatically joins store and category.
    """
    def get_queryset(self):
        return super().get_queryset().filter(
            is_active=True, is_archived=False
        ).filter(
            models.Q(publish_at__isnull=True) | models.Q(publish_at__lte=timezone.now())
        ).select_related('store', 'category').prefetch_related('images', 'tags')



class ProductGroup(models.Model):
    """
    Canonical product — represents a real-world item.
    Multiple sellers can link their Product to the same ProductGroup.
    Buyers see one card with all seller offers underneath.
    """
    title = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='product_groups'
    , db_index=True)
    description = models.TextField(blank=True)
    fingerprint = models.CharField(max_length=64, unique=True, db_index=True)
    image_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    # Brand alias map — sellers spell brands inconsistently. Anything in a
    # group canonicalises to the first entry. Add entries as we observe drift.
    BRAND_ALIASES = {
        'apple':       ['apple', 'apple inc', 'apple inc.'],
        'samsung':     ['samsung', 'samsung electronics'],
        'xiaomi':      ['xiaomi', 'mi', 'redmi'],
        'huawei':      ['huawei', 'honor'],
        'lg':          ['lg', 'lg electronics'],
        'sony':        ['sony', 'sony group'],
        'nike':        ['nike', 'nike inc'],
        'adidas':      ['adidas', 'adidas ag'],
        'puma':        ['puma', 'puma se'],
    }

    @classmethod
    def _normalize_title(cls, title: str) -> str:
        """Aggressive normalisation: lowercase, fold diacritics, collapse whitespace,
        strip punctuation. So "iPhone  15-Pro!" and "iphone 15 pro" hit the same key."""
        import re
        import unicodedata
        if not title:
            return ''
        s = unicodedata.normalize('NFKD', title.lower())
        s = ''.join(c for c in s if not unicodedata.combining(c))
        # Replace any non-alphanumeric with single space, collapse runs
        s = re.sub(r'[^a-z0-9]+', ' ', s)
        return ' '.join(s.split())

    @classmethod
    def _normalize_brand(cls, brand: str) -> str:
        """Map common variants to a canonical brand name. Falls back to
        normalised input when no alias hit."""
        norm = cls._normalize_title(brand)
        if not norm:
            return ''
        for canonical, aliases in cls.BRAND_ALIASES.items():
            if norm in aliases:
                return canonical
        return norm

    @classmethod
    def find_or_create(cls, title, brand, category):
        """Find existing group by deterministic normalised fingerprint or create new."""
        import hashlib
        raw = (
            f'{cls._normalize_title(title)}|'
            f'{cls._normalize_brand(brand or "")}|'
            f'{category.id if category else 0}'
        )
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:64]
        group, created = cls.objects.get_or_create(
            fingerprint=fingerprint,
            defaults={
                'title': title,
                'brand': brand or '',
                'category': category,
            }
        )
        return group, created

class Product(models.Model):
    SALE_CHOICES = (('sale', 'For Sale'), ('rent', 'For Rent'))
    CONDITION_CHOICES = (('new', 'New'), ('used', 'Used'), ('refurbished', 'Refurbished'))

    product_group = models.ForeignKey('ProductGroup', on_delete=models.SET_NULL, null=True, blank=True, related_name='seller_listings', db_index=True)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='products', db_index=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products', db_index=True)

    # FIX: Track who listed the product (multi-manager audit trail)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_products',
        help_text='Which team member listed this product'
    , db_index=True)

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, blank=True, unique=True)
    description = models.TextField(blank=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    condition = models.CharField(max_length=15, choices=CONDITION_CHOICES, default='new')
    sale_type = models.CharField(max_length=10, choices=SALE_CHOICES, default='sale')

    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    quantity = models.PositiveIntegerField(default=1)
    sku = models.CharField(max_length=100, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    low_stock_threshold = models.PositiveIntegerField(default=5)

    weight_kg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    length_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    width_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    is_archived = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_boosted = models.BooleanField(default=False)
    publish_at = models.DateTimeField(null=True, blank=True)

    warranty_info = models.TextField(blank=True, null=True)
    return_policy = models.TextField(blank=True, null=True)
    tags = models.ManyToManyField(ProductTag, blank=True, related_name='products')

    meta_title = models.CharField(max_length=200, blank=True, null=True)
    meta_description = models.TextField(blank=True, null=True)

    views = models.PositiveIntegerField(default=0)
    add_to_cart_count = models.PositiveIntegerField(default=0)
    wishlist_count = models.PositiveIntegerField(default=0)

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    image_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Postgres full-text search index — populated by signal on save / m2m change.
    # GIN-indexed for fast search; diacritic-folded so "telemovel" matches "telemóvel".
    # Stays NULL on SQLite (dev); search code falls back to LIKE there.
    from django.contrib.postgres.search import SearchVectorField
    search_vector = SearchVectorField(null=True, blank=True)

    # FIX: Custom manager with select_related pre-loaded — prevents N+1
    objects = models.Manager()  # Raw manager for admin
    active = ActiveProductManager()  # Use this in views

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['slug']),
            models.Index(fields=['sku']),
            models.Index(fields=['store', 'is_active', 'is_archived']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['is_active', 'is_archived', '-created_at']),
            models.Index(fields=['is_featured', 'is_active']),
            models.Index(fields=['price']),
            models.Index(fields=['publish_at', 'is_active']),
            models.Index(fields=['created_by']),
        ]

    def save(self, *args, **kwargs):
        # Stock-out auto-deactivation (legacy behaviour preserved)
        if self.quantity == 0 and self.is_active:
            self.is_active = False

        # Slug allocation: race-safe INSERT-then-retry. The previous
        # implementation did a .exists() pre-check then save — classic
        # TOCTOU: two concurrent product creates with the same title
        # both pass the check, then both INSERT and one collides.
        #
        # Pattern: pick base slug, try save; on IntegrityError that
        # mentions 'slug', append a short random suffix and retry.
        # Existing-row updates skip the loop entirely.
        from django.db import IntegrityError, transaction
        import secrets

        if self.pk is not None and self.slug:
            # Existing row, slug already set → no allocation needed
            super().save(*args, **kwargs)
            self._post_save_invalidations()
            return

        if not self.slug:
            self.slug = slugify(self.title) or 'product'
        base_slug = self.slug

        max_attempts = 5
        last_exc = None
        for attempt in range(max_attempts):
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                self._post_save_invalidations()
                return
            except IntegrityError as e:
                msg = str(e).lower()
                # Only retry on slug-related collisions; other unique
                # constraint failures are bugs we want surfaced.
                if 'slug' not in msg and 'uniq' not in msg:
                    raise
                last_exc = e
                # Append 6 random base32-ish chars (~30 bits of entropy).
                # Concurrent retries are extremely unlikely to collide.
                suffix = secrets.token_urlsafe(4).rstrip('=').lower()
                suffix = ''.join(c for c in suffix if c.isalnum())[:6]
                self.slug = f'{base_slug}-{suffix}'
        # Exhausted all attempts — re-raise the last collision.
        raise IntegrityError(
            f'Failed to allocate unique slug for {self.title!r} after '
            f'{max_attempts} attempts: {last_exc}'
        )

    def _post_save_invalidations(self):

        # Invalidate cached homepage sections
        from django.core.cache import cache
        cache.delete('homepage:trending')
        cache.delete('homepage:new_arrivals')
        cache.delete('homepage:featured')

        # Bump tag-versioned caches: any cache key that referenced
        # tag='product:{id}' becomes logically invalid on next read.
        try:
            from apps.core.cache_kit import bump_tag
            bump_tag(f'product:{self.id}')
        except Exception:
            pass

    @property
    def is_published(self):
        if self.publish_at and timezone.now() < self.publish_at:
            return False
        return self.is_active and not self.is_archived

    @property
    def discount_percentage(self):
        if self.compare_at_price and self.compare_at_price > self.price:
            return round(((self.compare_at_price - self.price) / self.compare_at_price) * 100, 1)
        return 0

    @property
    def is_low_stock(self):
        return 0 < self.quantity <= self.low_stock_threshold

    def __str__(self):
        return f"{self.title} ({self.store.name})"


class ProductImage(models.Model):
    @staticmethod
    def compute_hash(image_file):
        try:
            import imagehash
            from PIL import Image
            img = Image.open(image_file)
            return str(imagehash.phash(img))
        except Exception:
            return ''

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/images/')
    # Resized variants stored separately
    thumbnail_url = models.URLField(blank=True)
    medium_url = models.URLField(blank=True)
    large_url = models.URLField(blank=True)
    alt_text = models.CharField(max_length=200, blank=True)
    ordering = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ordering', 'created_at']
        indexes = [models.Index(fields=['product', 'ordering'])]


class ProductVideo(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='videos')
    video = models.FileField(upload_to='products/videos/')
    thumbnail = models.ImageField(upload_to='products/video_thumbnails/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ProductQA(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='questions')
    asker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_questions')
    question = models.TextField()
    answer = models.TextField(blank=True, null=True)
    answered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='product_answers')
    answered_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['product', 'is_published'])]


class PriceTier(models.Model):
    """Bulk pricing tier — "buy N+ get this unit price".

    Example for a t-shirt:
      base price = 3200 Kz
      PriceTier(min_quantity=5, unit_price=2800)
      PriceTier(min_quantity=10, unit_price=2400)
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_tiers')
    min_quantity = models.PositiveIntegerField(help_text='Buyer must buy at least this many for this tier')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['min_quantity']
        unique_together = ('product', 'min_quantity')
        indexes = [models.Index(fields=['product', 'min_quantity'])]

    def __str__(self):
        return f"{self.product.title} · {self.min_quantity}+ @ {self.unit_price}"

    @classmethod
    def price_for_quantity(cls, product, quantity, fallback):
        """Return the best (lowest) tier unit_price that applies for the given quantity,
        or `fallback` (typically product.price) when no tier qualifies."""
        try:
            tier = cls.objects.filter(
                product=product, min_quantity__lte=quantity
            ).order_by('-min_quantity').first()
            return tier.unit_price if tier else fallback
        except Exception:
            return fallback

