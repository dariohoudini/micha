from django.urls import path
from .views import (
    BlockUserView,
    UnblockUserView,
    BlockedUsersListView,
)

urlpatterns = [
    path("block/", BlockUserView.as_view(), name="block-user"),
    path("unblock/<int:user_id>/", UnblockUserView.as_view(), name="unblock-user"),
    path("blocked/", BlockedUsersListView.as_view(), name="blocked-users"),
]
