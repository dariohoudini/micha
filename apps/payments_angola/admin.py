from django.contrib import admin

from .models import (
    BankTransferProof, BuyerCodProfile, CodCashRemittance, CodCollection,
    CodEligibilityConfig, CodReconciliationException, CourierCashPosition,
    DunningState, MulticaixaReference, PaymentAuditEvent, PaymentComponent,
    PaymentFlow, PaymentsAngolaKpiSnapshot, SettlementRecord, SettlementRun,
    WalletIntegrityBreach, WalletLedgerEntry, WalletTransfer,
)


@admin.register(PaymentFlow)
class PaymentFlowAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_id', 'method', 'amount_cents', 'status',
                    'settled', 'paid_at', 'created_at')
    list_filter = ('method', 'status', 'settled')
    search_fields = ('order_id', 'idempotency_key', 'psp_reference')


@admin.register(PaymentComponent)
class PaymentComponentAdmin(admin.ModelAdmin):
    list_display = ('flow', 'method', 'amount_cents', 'status',
                    'hold_expires_at')
    list_filter = ('method', 'status')


@admin.register(PaymentAuditEvent)
class PaymentAuditEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'flow', 'correlation_id', 'created_at')
    list_filter = ('event_type',)
    readonly_fields = [f.name for f in PaymentAuditEvent._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CodEligibilityConfig)
class CodEligibilityConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'max_order_cents', 'min_order_cents',
                    'cod_fee_cents', 'updated_at')


@admin.register(BuyerCodProfile)
class BuyerCodProfileAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'refusal_count_90d', 'open_exposure_cents',
                    'cod_disabled')
    list_filter = ('cod_disabled',)


@admin.register(CodCollection)
class CodCollectionAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'courier', 'amount_cents', 'status',
                    'reconciled', 'collected_at')
    list_filter = ('status', 'reconciled')


@admin.register(CourierCashPosition)
class CourierCashPositionAdmin(admin.ModelAdmin):
    list_display = ('courier', 'cash_on_hand_cents', 'cash_shortfall_cents',
                    'cod_privilege_suspended', 'last_collection_at')
    list_filter = ('cod_privilege_suspended',)


@admin.register(CodCashRemittance)
class CodCashRemittanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'courier', 'expected_cents', 'deposited_cents',
                    'status', 'discrepancy_cents', 'collected_at')
    list_filter = ('status',)


@admin.register(CodReconciliationException)
class CodReconciliationExceptionAdmin(admin.ModelAdmin):
    list_display = ('courier', 'recon_date', 'expected_cents',
                    'collected_cents', 'banked_cents', 'resolved')
    list_filter = ('resolved',)


@admin.register(MulticaixaReference)
class MulticaixaReferenceAdmin(admin.ModelAdmin):
    list_display = ('reference', 'entity', 'amount_cents', 'is_active',
                    'paid', 'expires_at')
    list_filter = ('is_active', 'paid')
    search_fields = ('reference', 'psp_reference')


@admin.register(BankTransferProof)
class BankTransferProofAdmin(admin.ModelAdmin):
    list_display = ('flow', 'bank', 'declared_amount_cents', 'status',
                    'statement_matched', 'created_at')
    list_filter = ('status', 'bank', 'statement_matched')


@admin.register(WalletLedgerEntry)
class WalletLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'direction', 'amount_cents',
                    'balance_after_cents', 'reference_type', 'created_at')
    list_filter = ('direction', 'reference_type')
    search_fields = ('idempotency_key', 'reference_id')
    readonly_fields = [f.name for f in WalletLedgerEntry._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WalletIntegrityBreach)
class WalletIntegrityBreachAdmin(admin.ModelAdmin):
    list_display = ('user', 'ledger_balance_cents', 'cached_balance_cents',
                    'resolved', 'detected_at')
    list_filter = ('resolved',)


@admin.register(WalletTransfer)
class WalletTransferAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'recipient', 'amount_cents', 'status',
                    'created_at')
    list_filter = ('status',)


@admin.register(SettlementRecord)
class SettlementRecordAdmin(admin.ModelAdmin):
    list_display = ('settlement_date', 'psp_reference', 'gross_cents',
                    'fee_cents', 'net_cents', 'match_status')
    list_filter = ('match_status', 'settlement_date')


@admin.register(SettlementRun)
class SettlementRunAdmin(admin.ModelAdmin):
    list_display = ('run_date', 'total_internal_paid', 'matched',
                    'exceptions', 'match_rate_pct', 'status')
    list_filter = ('status',)


@admin.register(DunningState)
class DunningStateAdmin(admin.ModelAdmin):
    list_display = ('flow', 'reminders_sent', 'recovered', 'last_reminder_at')
    list_filter = ('recovered',)


@admin.register(PaymentsAngolaKpiSnapshot)
class PaymentsAngolaKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'payment_success_pct',
                    'cod_acceptance_pct', 'cod_refusal_pct',
                    'settlement_match_pct', 'wallet_integrity_ok')


from .models import ProcessedWebhookEvent


@admin.register(ProcessedWebhookEvent)
class ProcessedWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('provider', 'event_key', 'merchant_order_id', 'psp_status',
                    'received_at')
    list_filter = ('provider', 'psp_status')
    search_fields = ('event_key', 'merchant_order_id')
    readonly_fields = [f.name for f in ProcessedWebhookEvent._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
