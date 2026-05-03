from django.urls import path
from .views import TaskMonitoringView, TaskHealthView

urlpatterns = [
    path('tasks/', TaskMonitoringView.as_view(), name='task-monitoring'),
    path('tasks/health/', TaskHealthView.as_view(), name='task-health'),
]
