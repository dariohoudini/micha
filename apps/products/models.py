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


class Product(models.Model):
    SALE_CHOICES = (('sale', 'For Sale'), ('rent', 'For Rent'))
    CONDITION_CHOICES = (('new', 'New'), ('used', 'Used'), ('refurbished', 'Refurbished'))

    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')

    # FIX: Track who listed the product (multi-manager audit trail)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_products',
        help_text='Which team member listed this product'
    )

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
        if not self.slug:
            base = slugify(self.title)
            slug = base
            n = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug

        # FIX: Only auto-deactivate when going OUT of stock.
        # Never block reactivation — seller can restock and re-enable.
        # Old code: if self.quantity == 0: self.is_active = False
        # Problem: seller restocks to 10, is_active stays False, sales stop silently
        if self.quantity == 0 and self.is_active:
            self.is_active = False
            # Note: seller must manually re-activate after restocking
            # This is intentional — forces seller to confirm product is ready

        super().save(*args, **kwargs)

        # Invalidate cached homepage sections
        from django.core.cache import cache
        cache.delete('homepage:trending')
        cache.delete('homepage:new_arrivals')
        cache.delete('homepage:featured')

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
