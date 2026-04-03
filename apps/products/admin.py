from django.contrib import admin
from .models import Category, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'store', 'sale_type', 'price', 'quantity', 'is_archived')
    list_filter = ('sale_type', 'is_archived')
    search_fields = ('title',)


admin.site.register(Category)
