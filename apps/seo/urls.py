from django.urls import path
from .views import ProductSchemaView


urlpatterns = [
    path("schema/product/<int:product_id>/", ProductSchemaView.as_view(), name="product-schema"),
]
