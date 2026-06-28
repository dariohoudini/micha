from django.contrib import admin

from .models import (
    AccountingEvent, AccountingPeriod, AccountReceivable,
    CapitalisedDevelopment, DeferredRevenue, DisputeReserveLedger,
    EscrowLedger, FinancialStatementSnapshot, FxRevaluation, GLAccount,
    JournalEntry, JournalLine, ManualEntryApproval, SellerPayableLedger,
    SubLedgerReconciliation,
)


@admin.register(GLAccount)
class GLAccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'normal_balance',
                    'is_active')
    list_filter = ('account_type', 'normal_balance', 'is_active')
    search_fields = ('code', 'name')


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    list_display = ('period', 'is_locked', 'locked_by', 'locked_at')
    list_filter = ('is_locked',)


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    readonly_fields = ('account', 'debit_cents', 'credit_cents',
                       'description', 'party')

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'entry_date', 'period', 'description',
                    'source_type', 'total_cents', 'is_reversal', 'posted_at')
    list_filter = ('source_type', 'is_reversal', 'period')
    search_fields = ('source_id', 'description')
    inlines = [JournalLineInline]
    readonly_fields = [f.name for f in JournalEntry._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False  # immutable

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EscrowLedger)
class EscrowLedgerAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'seller', 'gross_amount_cents',
                    'commission_cents', 'net_seller_cents', 'status')
    list_filter = ('status', 'payment_method')
    search_fields = ('order_id',)


@admin.register(SellerPayableLedger)
class SellerPayableLedgerAdmin(admin.ModelAdmin):
    list_display = ('seller', 'order_id', 'net_cents', 'adjustments_cents',
                    'status', 'accrued_at', 'paid_at')
    list_filter = ('status',)
    search_fields = ('order_id',)


@admin.register(DisputeReserveLedger)
class DisputeReserveLedgerAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'open_dispute_value_cents',
                    'expected_loss_cents', 'adjustment_cents')


@admin.register(DeferredRevenue)
class DeferredRevenueAdmin(admin.ModelAdmin):
    list_display = ('seller', 'kind', 'total_cents', 'recognised_cents',
                    'months_recognised', 'months_total', 'is_active')
    list_filter = ('kind', 'is_active')


@admin.register(CapitalisedDevelopment)
class CapitalisedDevelopmentAdmin(admin.ModelAdmin):
    list_display = ('feature_name', 'capitalised_cents', 'amortised_cents',
                    'status', 'went_live_at')
    list_filter = ('status',)


@admin.register(AccountReceivable)
class AccountReceivableAdmin(admin.ModelAdmin):
    list_display = ('debtor', 'kind', 'amount_cents', 'recovered_cents',
                    'status', 'raised_at')
    list_filter = ('kind', 'status')


@admin.register(FxRevaluation)
class FxRevaluationAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'currency', 'foreign_amount',
                    'opening_rate', 'closing_rate', 'gain_loss_cents')
    list_filter = ('currency',)


@admin.register(SubLedgerReconciliation)
class SubLedgerReconciliationAdmin(admin.ModelAdmin):
    list_display = ('recon_date', 'ledger', 'sub_ledger_total_cents',
                    'gl_balance_cents', 'difference_cents', 'balanced')
    list_filter = ('ledger', 'balanced')


@admin.register(ManualEntryApproval)
class ManualEntryApprovalAdmin(admin.ModelAdmin):
    list_display = ('description', 'period', 'requested_by', 'approved_by',
                    'status', 'created_at')
    list_filter = ('status',)


@admin.register(FinancialStatementSnapshot)
class FinancialStatementSnapshotAdmin(admin.ModelAdmin):
    list_display = ('period', 'total_revenue_cents', 'gross_profit_cents',
                    'net_profit_cents', 'trial_balance_balanced',
                    'balance_sheet_balanced')


@admin.register(AccountingEvent)
class AccountingEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'actor', 'payload', 'created_at')
