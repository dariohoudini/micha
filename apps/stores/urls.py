from django.urls import path
from .views import MyStoreListView, PublicStoreListView, PublicStoreDetailView

app_name = "stores"

urlpatterns = [
    # Authenticated user's stores
    path("my/", MyStoreListView.as_view(), name="my-stores"),

    # Public stores list
    path("", PublicStoreListView.as_view(), name="public-stores"),

    # Public store detail (includes nested products)
    path("<int:pk>/", PublicStoreDetailView.as_view(), name="public-store-detail"),
]
