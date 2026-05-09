from django.contrib import admin
from .models import Account, Journal, LedgerEntry


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'type', 'user', 'currency', 'cached_balance_cents', 'is_active', 'updated_at')
    list_filter = ('type', 'currency', 'is_active')
    search_fields = ('user__email', 'name')
    readonly_fields = ('cached_balance_cents', 'cached_balance_at', 'created_at', 'updated_at')


class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    extra = 0
    can_delete = False
    readonly_fields = ('account', 'debit_cents', 'credit_cents', 'description', 'created_at')


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ('id', 'idempotency_key', 'ref_type', 'ref_id', 'description', 'created_at')
    list_filter = ('ref_type',)
    search_fields = ('idempotency_key', 'ref_id', 'description')
    readonly_fields = ('idempotency_key', 'description', 'ref_type', 'ref_id', 'posted_by', 'created_at')
    inlines = [LedgerEntryInline]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'account', 'debit_cents', 'credit_cents', 'description', 'created_at')
    list_filter = ('account__type',)
    search_fields = ('description', 'journal__idempotency_key')
    readonly_fields = ('journal', 'account', 'debit_cents', 'credit_cents', 'description', 'created_at')
