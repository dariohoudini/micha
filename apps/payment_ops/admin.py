from django.contrib import admin

from .models import (
    AmlAlert, B2BAccount, B2BInvoice, BnplInstalment,
    BnplInstalmentPlan, BnplProvider, BuyerWallet,
    BuyerWalletTransaction, ChargebackEvidence, ChargebackOutcome,
    CurrencyConversionDispute, FinancialReportSnapshot,
    FxHedgePosition, MultiCurrencyDisplay, PaymentFailureLog,
    PaymentMethodEligibilityRule, PaymentOpsEvent,
    PaymentOpsKpiSnapshot, PaymentRecoveryAttempt,
    ReconciliationException, SanctionsScreen, SarFiling,
    SellerAnnualTaxExport, SplitPaymentAllocation, StoreCredit,
    StoreCreditTransaction, TaxInvoice, TokenisedPaymentMethod,
    WalletTopUp,
)


@admin.register(ChargebackEvidence)
class ChargebackEvidenceAdmin(admin.ModelAdmin):
    list_display = ('chargeback_id', 'order_id', 'kind',
                    'uploaded_by', 'submitted_at')
    list_filter = ('kind',)


@admin.register(ChargebackOutcome)
class ChargebackOutcomeAdmin(admin.ModelAdmin):
    list_display = ('chargeback_id', 'outcome', 'recovery_amount',
                    'seller_liability_amount', 'decided_at')
    list_filter = ('outcome',)


@admin.register(ReconciliationException)
class ReconciliationExceptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'settlement_date', 'kind', 'order_id',
                    'expected_amount', 'actual_amount', 'resolved')
    list_filter = ('kind', 'resolved')


@admin.register(FxHedgePosition)
class FxHedgePositionAdmin(admin.ModelAdmin):
    list_display = ('pair', 'side', 'notional', 'booked_rate',
                    'settle_at', 'pnl', 'status')
    list_filter = ('status', 'side')


@admin.register(MultiCurrencyDisplay)
class MultiCurrencyDisplayAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'base_currency', 'base_amount',
                    'buyer_currency', 'display_amount', 'computed_at')
    list_filter = ('buyer_currency',)


@admin.register(TaxInvoice)
class TaxInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'kind', 'order_id',
                    'country', 'currency', 'total',
                    'voided', 'issued_at')
    list_filter = ('kind', 'voided', 'country')


@admin.register(AmlAlert)
class AmlAlertAdmin(admin.ModelAdmin):
    list_display = ('subject_user', 'kind', 'severity',
                    'total_amount', 'status', 'detected_at')
    list_filter = ('kind', 'status')


@admin.register(SarFiling)
class SarFilingAdmin(admin.ModelAdmin):
    list_display = ('sar_reference', 'alert', 'status',
                    'filer', 'filed_at')
    list_filter = ('status',)


@admin.register(SellerAnnualTaxExport)
class SellerAnnualTaxExportAdmin(admin.ModelAdmin):
    list_display = ('seller', 'tax_year', 'gross_sales',
                    'commissions_paid', 'net_payouts', 'currency')


@admin.register(PaymentMethodEligibilityRule)
class PaymentMethodEligibilityRuleAdmin(admin.ModelAdmin):
    list_display = ('method_code', 'country', 'currency',
                    'allow', 'priority', 'is_active')
    list_filter = ('allow', 'is_active', 'country')


@admin.register(BnplProvider)
class BnplProviderAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'countries',
                    'max_order_value', 'currency', 'is_active')
    list_filter = ('is_active', 'currency')


@admin.register(BnplInstalmentPlan)
class BnplInstalmentPlanAdmin(admin.ModelAdmin):
    list_display = ('provider', 'buyer', 'order_id',
                    'total_amount', 'instalments',
                    'instalments_paid', 'status')
    list_filter = ('status', 'provider')


@admin.register(BnplInstalment)
class BnplInstalmentAdmin(admin.ModelAdmin):
    list_display = ('plan', 'sequence_number', 'amount',
                    'due_at', 'paid_at', 'days_late', 'status')
    list_filter = ('status',)


@admin.register(StoreCredit)
class StoreCreditAdmin(admin.ModelAdmin):
    list_display = ('user', 'remaining_amount', 'currency',
                    'reason', 'status', 'expires_at')
    list_filter = ('status', 'reason', 'currency')


@admin.register(StoreCreditTransaction)
class StoreCreditTransactionAdmin(admin.ModelAdmin):
    list_display = ('credit', 'kind', 'amount',
                    'related_order_id', 'occurred_at')
    list_filter = ('kind',)


@admin.register(B2BAccount)
class B2BAccountAdmin(admin.ModelAdmin):
    list_display = ('legal_name', 'tax_id', 'country', 'status',
                    'credit_limit', 'available_credit',
                    'payment_terms_days')
    list_filter = ('status', 'country')


@admin.register(B2BInvoice)
class B2BInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'account', 'order_id',
                    'amount', 'paid_amount', 'status',
                    'due_at', 'days_overdue')
    list_filter = ('status',)


@admin.register(SplitPaymentAllocation)
class SplitPaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'sequence_number', 'method_code',
                    'amount', 'currency', 'status', 'created_at')
    list_filter = ('status', 'method_code')


@admin.register(BuyerWallet)
class BuyerWalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'available_balance', 'pending_balance',
                    'currency', 'daily_spend_limit', 'is_active')
    list_filter = ('is_active', 'currency')


@admin.register(BuyerWalletTransaction)
class BuyerWalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'kind', 'amount', 'currency',
                    'balance_after', 'related_order_id', 'occurred_at')
    list_filter = ('kind',)


@admin.register(WalletTopUp)
class WalletTopUpAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'amount', 'currency', 'gateway',
                    'status', 'created_at', 'completed_at')
    list_filter = ('status', 'gateway')


@admin.register(PaymentFailureLog)
class PaymentFailureLogAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'buyer', 'category', 'failure_code',
                    'amount', 'currency', 'occurred_at')
    list_filter = ('category', 'gateway')


@admin.register(PaymentRecoveryAttempt)
class PaymentRecoveryAttemptAdmin(admin.ModelAdmin):
    list_display = ('failure', 'strategy', 'attempt_number',
                    'scheduled_at', 'outcome', 'executed_at')
    list_filter = ('strategy', 'outcome')


@admin.register(CurrencyConversionDispute)
class CurrencyConversionDisputeAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'buyer', 'displayed_amount',
                    'charged_amount', 'difference', 'status',
                    'filed_at')
    list_filter = ('status',)


@admin.register(FinancialReportSnapshot)
class FinancialReportSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'gmv', 'net_revenue',
                    'refund_rate', 'chargeback_rate', 'gross_profit')


@admin.register(SanctionsScreen)
class SanctionsScreenAdmin(admin.ModelAdmin):
    list_display = ('subject_user', 'context', 'list_source',
                    'match_confidence', 'action_taken', 'occurred_at')
    list_filter = ('context', 'list_source', 'action_taken')


@admin.register(TokenisedPaymentMethod)
class TokenisedPaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('user', 'gateway', 'method_type', 'brand',
                    'last_four', 'is_active', 'created_at')
    list_filter = ('gateway', 'method_type', 'is_active')


@admin.register(PaymentOpsKpiSnapshot)
class PaymentOpsKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'transaction_count',
                    'auth_rate_pct', 'chargeback_rate_pct',
                    'fx_pnl', 'aml_alerts_open')


@admin.register(PaymentOpsEvent)
class PaymentOpsEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'order_id', 'user', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'payload', 'created_at',
                       'order_id', 'user', 'actor')
