from django.urls import path

from . import views

app_name = 'admin_console'

urlpatterns = [
    # CH1 RBAC + dual approval
    path('me/role/', views.MyRoleView.as_view(), name='my-role'),
    path('approvals/', views.ApprovalListView.as_view(), name='approvals'),
    path('approvals/<int:request_id>/decision/',
         views.ApprovalDecisionView.as_view(), name='approval-decision'),
    # CH3 commission override
    path('commission-overrides/', views.CommissionOverrideView.as_view(),
         name='commission-override'),
    # CH4 personalisation
    path('personalisation/config/', views.PersonalisationConfigView.as_view(),
         name='personalisation-config'),
    path('personalisation/config/<int:config_id>/deploy/',
         views.PersonalisationDeployView.as_view(),
         name='personalisation-deploy'),
    # CH5 experiments
    path('experiments/', views.ExperimentView.as_view(), name='experiments'),
    path('experiments/<int:experiment_id>/decision/',
         views.ExperimentDecisionView.as_view(), name='experiment-decision'),
    # CH10 fee schedule
    path('fee-schedule/', views.FeeScheduleView.as_view(), name='fee-schedule'),
    # CH13 system config
    path('settings/', views.PlatformSettingView.as_view(), name='settings'),
    path('kill-switches/', views.KillSwitchView.as_view(),
         name='kill-switches'),
    # CH16 data export
    path('data-exports/', views.DataExportView.as_view(), name='data-exports'),
    # CH18 legal
    path('legal-holds/', views.LegalHoldView.as_view(), name='legal-holds'),
    path('le-requests/', views.LeRequestView.as_view(), name='le-requests'),
    # CH21 banners
    path('banners/', views.BannerView.as_view(), name='banners'),
    path('banners/<int:banner_id>/approve/', views.BannerApproveView.as_view(),
         name='banner-approve'),
    # CH22 platform alerts
    path('platform-alerts/', views.PlatformAlertView.as_view(),
         name='platform-alerts'),
    # CH23 incident command
    path('service-status/', views.ServiceStatusView.as_view(),
         name='service-status'),
    path('incidents/', views.IncidentView.as_view(), name='incidents'),
    # CH24 KPIs
    path('kpis/', views.AdminKpiView.as_view(), name='kpis'),
]
