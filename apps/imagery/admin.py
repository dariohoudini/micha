from django.contrib import admin
from .models import ImageSource, ImageVariant


@admin.register(ImageSource)
class ImageSourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'sha256_short', 'content_type', 'width',
                    'height', 'bytes_size', 'status', 'uploaded_by',
                    'created_at')
    list_filter = ('status', 'content_type')
    search_fields = ('sha256',)
    readonly_fields = ('sha256', 'original_path', 'content_type', 'width',
                       'height', 'bytes_size', 'created_at', 'updated_at')

    def sha256_short(self, obj):
        return obj.sha256[:12] + '…'


@admin.register(ImageVariant)
class ImageVariantAdmin(admin.ModelAdmin):
    list_display = ('id', 'source', 'variant', 'format',
                    'width', 'height', 'bytes_size', 'created_at')
    list_filter = ('variant', 'format')
    search_fields = ('source__sha256',)
    readonly_fields = tuple(f.name for f in ImageVariant._meta.fields)
