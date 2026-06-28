"""
Seller onboarding URL map. Wired into config/urls.py under
/api/v1/seller-onboarding/.
"""
from django.urls import path

from .views import (
    AdminApplicationQueueView, AdminKycDecisionView,
    AgreementForApplicationView, AgreementSignView,
    ApplicationEventsView, ApplicationListCreateView,
    ApplicationSubmitView, CategoryEnrolmentView,
    CategoryUpgradeRequestView, FeeInvoicePayView,
    HolidayModeView, KycDocumentUploadView, LeadCreateView,
    MyHealthScoreView, MyTierView, ReactivationRequestView,
    SellerBrandView, TrainingProgressView, WizardStatusView,
    brand_name_check, recalculate_tier_now,
)
from .views_ext import (
    ApiKeyListCreateView, ApiKeyRevokeView, ChoiceApplyView,
    ChoiceEligibilityView, DeregistrationView, EmailLogListView,
    FunnelSnapshotView, MyChoiceEnrolmentsView, MyRebatesView,
    MyStoreTypeView, OfficialBrandStoreApplyView,
    WebhookDeliveryListView, WebhookEndpointDeleteView,
    WebhookEndpointListCreateView, compute_rebate,
    trigger_transactional_email,
)

urlpatterns = [
    # ── CH1: leads (public) ──────────────────────────────────────
    path('leads/', LeadCreateView.as_view(), name='leads-create'),

    # ── CH2: applications ────────────────────────────────────────
    path('applications/', ApplicationListCreateView.as_view(),
         name='applications'),
    path('applications/<uuid:pk>/submit/',
         ApplicationSubmitView.as_view(), name='application-submit'),
    path('applications/<uuid:pk>/events/',
         ApplicationEventsView.as_view(), name='application-events'),

    # ── CH3: KYC ────────────────────────────────────────────────
    path('applications/<uuid:pk>/kyc-documents/',
         KycDocumentUploadView.as_view(), name='kyc-document-upload'),

    # ── CH4: agreement ──────────────────────────────────────────
    path('applications/<uuid:pk>/agreement/',
         AgreementForApplicationView.as_view(), name='agreement-current'),
    path('agreements/<str:token>/sign/',
         AgreementSignView.as_view(), name='agreement-sign'),

    # ── CH5: fee ────────────────────────────────────────────────
    path('fee-invoices/<uuid:pk>/mark-paid/',
         FeeInvoicePayView.as_view(), name='fee-mark-paid'),

    # ── CH7: wizard ─────────────────────────────────────────────
    path('wizard/', WizardStatusView.as_view(), name='wizard'),

    # ── CH8: training ───────────────────────────────────────────
    path('training/progress/', TrainingProgressView.as_view(),
         name='training-progress'),

    # ── CH10: category enrolment ────────────────────────────────
    path('category-enrolments/', CategoryEnrolmentView.as_view(),
         name='category-enrolments'),

    # ── CH11: upgrades ──────────────────────────────────────────
    path('category-upgrades/', CategoryUpgradeRequestView.as_view(),
         name='category-upgrades'),

    # ── CH12: brand ─────────────────────────────────────────────
    path('brands/', SellerBrandView.as_view(), name='brands'),
    path('brands/check/', brand_name_check, name='brand-name-check'),

    # ── CH14: tier ──────────────────────────────────────────────
    path('tier/me/', MyTierView.as_view(), name='tier-me'),
    path('tier/recalculate-now/', recalculate_tier_now,
         name='tier-recalculate'),

    # ── CH16: health ────────────────────────────────────────────
    path('health/me/', MyHealthScoreView.as_view(), name='health-me'),

    # ── CH18: holiday ───────────────────────────────────────────
    path('holiday-mode/', HolidayModeView.as_view(), name='holiday-mode'),

    # ── CH20: reactivation ─────────────────────────────────────
    path('reactivation/', ReactivationRequestView.as_view(),
         name='reactivation'),

    # ── CH6 — Email drip + transactional ───────────────────────
    path('emails/me/', EmailLogListView.as_view(), name='emails-me'),
    path('emails/transactional/', trigger_transactional_email,
         name='emails-transactional'),

    # ── CH13 — Store types ─────────────────────────────────────
    path('store-types/me/', MyStoreTypeView.as_view(),
         name='store-type-me'),
    path('store-types/official-brand/apply/',
         OfficialBrandStoreApplyView.as_view(),
         name='official-brand-apply'),

    # ── CH17 — GMV rebates ─────────────────────────────────────
    path('rebates/me/', MyRebatesView.as_view(), name='rebates-me'),
    path('admin/rebates/compute/', compute_rebate,
         name='admin-compute-rebate'),

    # ── CH19 — Open Platform API + webhooks ────────────────────
    path('api-keys/', ApiKeyListCreateView.as_view(), name='api-keys'),
    path('api-keys/<uuid:pk>/revoke/', ApiKeyRevokeView.as_view(),
         name='api-key-revoke'),
    path('webhooks/', WebhookEndpointListCreateView.as_view(),
         name='webhooks'),
    path('webhooks/<uuid:pk>/', WebhookEndpointDeleteView.as_view(),
         name='webhook-disable'),
    path('webhooks/<uuid:pk>/deliveries/',
         WebhookDeliveryListView.as_view(), name='webhook-deliveries'),

    # ── CH21 — Voluntary deregistration ────────────────────────
    path('deregistration/', DeregistrationView.as_view(),
         name='deregistration'),

    # ── CH22 — Choice programme ────────────────────────────────
    path('choice/eligibility/', ChoiceEligibilityView.as_view(),
         name='choice-eligibility'),
    path('choice/apply/', ChoiceApplyView.as_view(),
         name='choice-apply'),
    path('choice/me/', MyChoiceEnrolmentsView.as_view(),
         name='choice-me'),

    # ── CH24 — Acquisition funnel KPIs ─────────────────────────
    path('admin/funnel/', FunnelSnapshotView.as_view(),
         name='admin-funnel'),

    # ── Admin ──────────────────────────────────────────────────
    path('admin/applications/queue/', AdminApplicationQueueView.as_view(),
         name='admin-application-queue'),
    path('admin/applications/<uuid:pk>/kyc-decide/',
         AdminKycDecisionView.as_view(), name='admin-kyc-decide'),
]
