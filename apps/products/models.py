from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

# ------------------------------
# Category Model
# ------------------------------
class Category(models.Model):
    name = models.CharField(max_length=100)
    is_custom = models.BooleanField(default=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='custom_categories'
    )

    class Meta:
        unique_together = ('owner', 'name')  # ensure no duplicate category names per user
        ordering = ['name']

    def __str__(self):
        return self.name

# ------------------------------
# Product Model
# ------------------------------
class Product(models.Model):
    SALE_TYPE_CHOICES = (
        ('sale', 'For Sale'),
        ('rent', 'For Rent'),
    )

    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='products'
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    sale_type = models.CharField(max_length=10, choices=SALE_TYPE_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    is_archived = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)  # for public listing

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.quantity == 0:
            self.is_archived = True
            self.is_active = False
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.store.name})"

# ------------------------------
# Product Images
# ------------------------------
class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images'
    )

    image = models.ImageField(upload_to='products/images/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.product.title}"
