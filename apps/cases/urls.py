from django.urls import path
from .views import (
    CaseListView, CaseDetailView, CaseResolveView, CaseReopenView,
    CaseLinkView, CaseNoteView, CaseSubjectView,
)

urlpatterns = [
    path('', CaseListView.as_view(), name='cases-list'),
    path('<int:pk>/', CaseDetailView.as_view(), name='cases-detail'),
    path('<int:pk>/resolve/', CaseResolveView.as_view(), name='cases-resolve'),
    path('<int:pk>/reopen/', CaseReopenView.as_view(), name='cases-reopen'),
    path('<int:pk>/links/', CaseLinkView.as_view(), name='cases-links'),
    path('<int:pk>/links/<int:link_id>/', CaseLinkView.as_view(), name='cases-link-detail'),
    path('<int:pk>/notes/', CaseNoteView.as_view(), name='cases-notes'),
    path('<int:pk>/subjects/', CaseSubjectView.as_view(), name='cases-subjects'),
]
