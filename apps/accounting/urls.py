from django.urls import path

from . import views

app_name = 'accounting'

urlpatterns = [
    path('accounts/', views.ChartOfAccountsView.as_view(), name='accounts'),
    path('trial-balance/', views.TrialBalanceView.as_view(),
         name='trial-balance'),
    path('profit-and-loss/', views.ProfitAndLossView.as_view(), name='pnl'),
    path('balance-sheet/', views.BalanceSheetView.as_view(),
         name='balance-sheet'),
    path('journals/', views.JournalListView.as_view(), name='journals'),
    path('reconciliations/', views.ReconciliationView.as_view(),
         name='reconciliations'),
    path('manual-entries/', views.ManualEntryView.as_view(),
         name='manual-entries'),
    path('manual-entries/<int:entry_id>/approve/',
         views.ManualEntryApproveView.as_view(), name='manual-entry-approve'),
    path('periods/', views.PeriodLockView.as_view(), name='periods'),
    path('month-end-close/', views.MonthEndCloseView.as_view(),
         name='month-end-close'),
    path('statements/', views.StatementSnapshotView.as_view(),
         name='statements'),
]
