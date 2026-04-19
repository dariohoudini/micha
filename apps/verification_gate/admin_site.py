"""
apps/verification_gate/admin_site.py

Django admin panel for reviewing verifications.
Admins see: photos, typed info, approve/reject buttons.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import SellerVerification, MonthlySelfie, VerificationAuditLog


@admin.register(SellerVerification)
class SellerVerificationAdmin(admin.ModelAdmin):
    list_display = [
        'seller_email', 'full_name', 'bi_number', 'status',
        'is_active', 'bi_expiry_date', 'days_until_expiry',
        'next_selfie_due', 'submission_count', 'updated_at'
    ]
    list_filter = ['status', 'is_active', 'issuing_province']
    search_fields = ['seller__email', 'full_name', 'bi_number']
    readonly_fields = [
        'id', 'seller', 'submission_count', 'first_submitted_at',
        'approved_at', 'locked_at', 'bi_front_preview',
        'bi_back_preview', 'selfie_preview', 'created_at', 'updated_at'
    ]
    ordering = ['-updated_at']

    fieldsets = [
        ('Vendedor', {
            'fields': ['id', 'seller', 'status', 'is_active', 'lock_reason']
        }),
        ('Documentos de Identidade', {
            'fields': [
                'bi_front_preview', 'bi_back_preview', 'selfie_preview',
                'bi_front_photo', 'bi_back_photo', 'initial_selfie',
            ]
        }),
        ('Dados do BI (digitados pelo vendedor)', {
            'fields': [
                'full_name', 'bi_number', 'date_of_birth',
                'place_of_birth', 'issuing_province',
                'bi_issue_date', 'bi_expiry_date',
            ]
        }),
        ('Revisão', {
            'fields': [
                'reviewed_by', 'reviewed_at',
                'rejection_reason', 'rejection_notes',
                'submission_count',
            ]
        }),
        ('Selfie Mensal', {
            'fields': ['last_selfie_date', 'next_selfie_due']
        }),
        ('Histórico', {
            'fields': ['first_submitted_at', 'approved_at', 'locked_at', 'created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    def seller_email(self, obj):
        return obj.seller.email
    seller_email.short_description = 'Email'

    def days_until_expiry(self, obj):
        days = obj.days_until_bi_expiry
        if days is None:
            return '—'
        if days <= 0:
            return format_html('<span style="color:red;font-weight:bold">EXPIRADO</span>')
        if days <= 14:
            return format_html(f'<span style="color:orange;font-weight:bold">{days} dias</span>')
        return f'{days} dias'
    days_until_expiry.short_description = 'Expira em'

    def bi_front_preview(self, obj):
        if obj.bi_front_photo:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-height:200px;max-width:300px;border:1px solid #ccc;border-radius:4px"/>'
                '</a><br><small>Clique para ver em tamanho real</small>',
                obj.bi_front_photo.url, obj.bi_front_photo.url
            )
        return '(sem foto)'
    bi_front_preview.short_description = '📄 Frente do BI'

    def bi_back_preview(self, obj):
        if obj.bi_back_photo:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-height:200px;max-width:300px;border:1px solid #ccc;border-radius:4px"/>'
                '</a>',
                obj.bi_back_photo.url, obj.bi_back_photo.url
            )
        return '(sem foto)'
    bi_back_preview.short_description = '📄 Verso do BI'

    def selfie_preview(self, obj):
        if obj.initial_selfie:
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-height:200px;max-width:200px;border-radius:50%;border:3px solid #C9A84C"/>'
                '</a>',
                obj.initial_selfie.url, obj.initial_selfie.url
            )
        return '(sem selfie)'
    selfie_preview.short_description = '🤳 Selfie'

    actions = ['approve_selected', 'reject_selected']

    def approve_selected(self, request, queryset):
        count = 0
        for v in queryset.filter(status='pending'):
            v.approve(reviewed_by=request.user)
            count += 1
        self.message_user(request, f'{count} verificações aprovadas.')
    approve_selected.short_description = '✅ Aprovar seleccionadas'

    def reject_selected(self, request, queryset):
        count = 0
        for v in queryset.filter(status='pending'):
            v.reject(reviewed_by=request.user, reason='image_unclear')
            count += 1
        self.message_user(request, f'{count} verificações rejeitadas (motivo: imagem ilegível).')
    reject_selected.short_description = '❌ Rejeitar (imagem ilegível)'


@admin.register(MonthlySelfie)
class MonthlySelfieAdmin(admin.ModelAdmin):
    list_display = [
        'seller_name', 'status', 'submitted_at', 'reviewed_at', 'selfie_preview'
    ]
    list_filter = ['status']
    readonly_fields = ['selfie_preview', 'submitted_at']
    ordering = ['-submitted_at']

    def seller_name(self, obj):
        return obj.verification.full_name or obj.verification.seller.email
    seller_name.short_description = 'Vendedor'

    def selfie_preview(self, obj):
        if obj.selfie:
            return format_html(
                '<img src="{}" style="max-height:150px;max-width:150px;border-radius:50%;border:3px solid #C9A84C"/>',
                obj.selfie.url
            )
        return '(sem selfie)'
    selfie_preview.short_description = '🤳 Selfie'

    actions = ['approve_selfies']

    def approve_selfies(self, request, queryset):
        count = 0
        for selfie in queryset.filter(status='pending'):
            selfie.approve(reviewed_by=request.user)
            count += 1
        self.message_user(request, f'{count} selfies aprovadas.')
    approve_selfies.short_description = '✅ Aprovar selfies seleccionadas'


@admin.register(VerificationAuditLog)
class VerificationAuditLogAdmin(admin.ModelAdmin):
    list_display = ['verification', 'action', 'performed_by', 'created_at']
    list_filter = ['action']
    readonly_fields = ['verification', 'action', 'performed_by', 'details', 'created_at']
    ordering = ['-created_at']
