"""
apps/rentals/urls.py
"""
from django.urls import path
from . import flows, views

urlpatterns = [
    # Meta — constants for frontend forms
    path('meta/', views.RentalsMetaView.as_view()),

    # Browse & search (public)
    path('browse/', views.ListingBrowseView.as_view()),
    path('<uuid:pk>/', views.ListingDetailView.as_view()),

    # My listings (lister)
    path('my/', views.MyListingsView.as_view()),
    path('create/', views.CreateListingView.as_view()),
    path('<uuid:pk>/update/', views.UpdateListingView.as_view()),
    path('<uuid:pk>/delete/', views.DeleteListingView.as_view()),
    path('<uuid:pk>/publish/', views.PublishListingView.as_view()),
    path('<uuid:pk>/pause/', views.PauseListingView.as_view()),
    path('<uuid:pk>/mark-rented/', views.MarkRentedView.as_view()),

    # Images
    path('<uuid:pk>/images/', views.UploadListingImageView.as_view()),

    # Inquiry / chat bridge
    path('<uuid:pk>/inquire/', views.CreateInquiryView.as_view()),

    # Property Vertical doc CH11/CH12 — viewings + offer negotiation
    path('<uuid:pk>/viewings/', flows.RequestViewingView.as_view()),
    path('viewings/', flows.MyViewingsView.as_view()),
    path('viewings/<uuid:pk>/action/', flows.ViewingActionView.as_view()),
    path('<uuid:pk>/offers/', flows.SubmitOfferView.as_view()),
    path('offers/', flows.MyOffersView.as_view()),
    path('offers/<uuid:pk>/action/', flows.OfferActionView.as_view()),
    path('offers/<uuid:pk>/history/', flows.OfferHistoryView.as_view()),

    # Save / unsave
    path('<uuid:pk>/save/', views.SaveListingView.as_view()),
    path('saved/', views.SavedListingsView.as_view()),

    # Verification
    path('verify/', views.SubmitVerificationView.as_view()),

    # Admin
    path('admin/verifications/', views.AdminVerificationsView.as_view()),
    path('admin/listings/', views.AdminListingsView.as_view()),
]
