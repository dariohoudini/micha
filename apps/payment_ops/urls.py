from django.urls import path

from .views import (
    FinancialReportView, MyStoreCreditView, MyWalletView,
    PaymentOpsKpiView, ReconciliationQueueView,
    aml_alert_raise, aml_escalate_sar, annual_tax_export_generate,
    b2b_account_approve, b2b_invoice_issue, b2b_invoice_pay,
    bnpl_create_plan, bnpl_mark_paid, chargeback_evidence_add,
    chargeback_evidence_submit, chargeback_outcome_record,
    display_price_snapshot, fx_dispute_file, fx_dispute_resolve,
    fx_hedge_book, fx_hedge_settle, payment_failure_record,
    payment_methods_eligible, recon_resolve,
    recovery_attempt_execute, sanctions_screen, sar_file,
    split_allocate, store_credit_grant, store_credit_spend,
    tax_invoice_issue, tax_invoice_void, token_register,
    token_revoke, wallet_spend, wallet_topup_confirm,
    wallet_topup_create,
)


urlpatterns = [
    # CH2 — chargeback
    path('chargebacks/evidence/', chargeback_evidence_add, name='po-cb-evidence'),
    path('chargebacks/evidence/submit/', chargeback_evidence_submit, name='po-cb-submit'),
    path('chargebacks/outcome/', chargeback_outcome_record, name='po-cb-outcome'),
    # CH3 — reconciliation
    path('recon/queue/', ReconciliationQueueView.as_view(), name='po-recon-queue'),
    path('recon/resolve/', recon_resolve, name='po-recon-resolve'),
    # CH4 — FX hedge
    path('fx/hedge/book/', fx_hedge_book, name='po-fx-hedge-book'),
    path('fx/hedge/settle/', fx_hedge_settle, name='po-fx-hedge-settle'),
    # CH5 — display price
    path('display-price/snapshot/', display_price_snapshot, name='po-display-snapshot'),
    # CH7 — tax invoice
    path('tax-invoices/issue/', tax_invoice_issue, name='po-tax-issue'),
    path('tax-invoices/void/', tax_invoice_void, name='po-tax-void'),
    # CH9 — AML / SAR
    path('aml/alerts/raise/', aml_alert_raise, name='po-aml-alert'),
    path('aml/alerts/escalate/', aml_escalate_sar, name='po-aml-escalate'),
    path('aml/sar/file/', sar_file, name='po-sar-file'),
    # CH10 — annual tax export
    path('tax/annual-export/', annual_tax_export_generate, name='po-annual-export'),
    # CH11 — eligibility
    path('methods/eligible/', payment_methods_eligible, name='po-eligible'),
    # CH12 — BNPL
    path('bnpl/plans/', bnpl_create_plan, name='po-bnpl-create'),
    path('bnpl/instalments/mark-paid/', bnpl_mark_paid, name='po-bnpl-mark-paid'),
    # CH13 — store credit
    path('store-credit/grant/', store_credit_grant, name='po-sc-grant'),
    path('store-credit/spend/', store_credit_spend, name='po-sc-spend'),
    path('store-credit/me/', MyStoreCreditView.as_view(), name='po-sc-me'),
    # CH15 — B2B
    path('b2b/accounts/approve/', b2b_account_approve, name='po-b2b-approve'),
    path('b2b/invoices/issue/', b2b_invoice_issue, name='po-b2b-issue'),
    path('b2b/invoices/pay/', b2b_invoice_pay, name='po-b2b-pay'),
    # CH16 — split payment
    path('split/allocate/', split_allocate, name='po-split-allocate'),
    # CH18 — wallet
    path('wallet/me/', MyWalletView.as_view(), name='po-wallet-me'),
    path('wallet/topup/create/', wallet_topup_create, name='po-wallet-topup'),
    path('wallet/topup/confirm/', wallet_topup_confirm, name='po-wallet-topup-confirm'),
    path('wallet/spend/', wallet_spend, name='po-wallet-spend'),
    # CH19 — failure + recovery
    path('failures/record/', payment_failure_record, name='po-failure'),
    path('recovery/execute/', recovery_attempt_execute, name='po-recovery'),
    # CH20 — FX dispute
    path('fx-disputes/', fx_dispute_file, name='po-fx-dispute'),
    path('fx-disputes/resolve/', fx_dispute_resolve, name='po-fx-dispute-resolve'),
    # CH21 — financial report
    path('admin/financial-report/', FinancialReportView.as_view(), name='po-fin-report'),
    # CH22 — sanctions
    path('sanctions/screen/', sanctions_screen, name='po-sanctions'),
    # CH23 — tokenisation
    path('tokens/register/', token_register, name='po-token-register'),
    path('tokens/revoke/', token_revoke, name='po-token-revoke'),
    # CH24 — KPI
    path('admin/kpi/', PaymentOpsKpiView.as_view(), name='po-kpi'),
]
