from django.urls import path

from .views import (
    AcquisitionChannelSpendListView, BuyerKpiSnapshotView,
    MyAttributionView, MyBirthdayRewardsView, MyDormancyView,
    MyEngagementEventsView, MyHomeFeedView, MyLTVView,
    MyMembershipView, MyRecoverySequencesView, MyShareStatsView,
    MyWelcomeIncentiveView, MyWinBackRunsView,
    SeasonalCampaignListView, campaign_join, first_purchase_record,
    first_purchase_verify, grant_welcome_view, home_feed_recompute,
    membership_charge, record_attribution_view,
    record_browse_signal_view, recovery_start,
    render_template_view, share_click, share_create,
)

urlpatterns = [
    # CH2 — attribution
    path('attribution/touch/', record_attribution_view, name='attribution-touch'),
    path('attribution/me/', MyAttributionView.as_view(), name='attribution-me'),

    # CH3 — welcome
    path('welcome/me/', MyWelcomeIncentiveView.as_view(), name='welcome-me'),
    path('welcome/grant/', grant_welcome_view, name='welcome-grant'),

    # CH4 — first purchase (admin/internal)
    path('first-purchase/record/', first_purchase_record, name='first-purchase-record'),
    path('first-purchase/verify/', first_purchase_verify, name='first-purchase-verify'),

    # CH10 — premium membership
    path('membership/me/', MyMembershipView.as_view(), name='membership-me'),
    path('membership/charge/', membership_charge, name='membership-charge'),

    # CH11/12 — recovery sequences
    path('recovery/me/', MyRecoverySequencesView.as_view(), name='recovery-me'),
    path('recovery/start/', recovery_start, name='recovery-start'),

    # CH13 — browse abandonment
    path('browse/abandon/', record_browse_signal_view, name='browse-abandon'),

    # CH16 — dormancy + win-back
    path('dormancy/me/', MyDormancyView.as_view(), name='dormancy-me'),
    path('winback/me/', MyWinBackRunsView.as_view(), name='winback-me'),

    # CH20 — birthday
    path('birthday/me/', MyBirthdayRewardsView.as_view(), name='birthday-me'),

    # CH21 — seasonal campaigns
    path('campaigns/active/', SeasonalCampaignListView.as_view(), name='campaigns-active'),
    path('campaigns/<slug:slug>/join/', campaign_join, name='campaigns-join'),

    # CH22 — social share
    path('shares/', share_create, name='shares-create'),
    path('shares/me/', MyShareStatsView.as_view(), name='shares-me'),
    path('s/<str:short_code>/', share_click, name='share-click'),

    # CH23 — LTV
    path('ltv/me/', MyLTVView.as_view(), name='ltv-me'),

    # CH24 — KPIs (admin)
    path('admin/buyer-kpis/', BuyerKpiSnapshotView.as_view(), name='admin-buyer-kpis'),
    path('admin/channel-spend/', AcquisitionChannelSpendListView.as_view(), name='admin-channel-spend'),

    # Audit
    path('events/me/', MyEngagementEventsView.as_view(), name='events-me'),

    # CH19 — personalised home feed
    path('home-feed/me/', MyHomeFeedView.as_view(), name='home-feed-me'),
    path('home-feed/recompute/', home_feed_recompute, name='home-feed-recompute'),

    # Template render
    path('templates/render/', render_template_view, name='template-render'),
]
