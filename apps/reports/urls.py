from django.urls import path
from .views import ReportCreateView, AdminReportListView, AdminReportUpdateView


urlpatterns = [
    path('create/', ReportCreateView.as_view(), name='report-create'),
    path('admin/', AdminReportListView.as_view(), name='admin-report-list'),
    path('admin/<int:pk>/', AdminReportUpdateView.as_view(), name='admin-report-update'),
]
