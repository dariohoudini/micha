from django.urls import path
from .views import BulkJobListView, BulkJobDetailView, BulkJobCancelView

urlpatterns = [
    path('', BulkJobListView.as_view(), name='bulk-jobs'),
    path('<int:pk>/', BulkJobDetailView.as_view(), name='bulk-job-detail'),
    path('<int:pk>/cancel/', BulkJobCancelView.as_view(), name='bulk-job-cancel'),
]
