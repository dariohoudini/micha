from django.urls import path
from .views import *
urlpatterns=[
    path('currencies/',CurrencyListView.as_view(),name='currencies'),
    path('languages/',LanguageListView.as_view(),name='languages'),
    path('translations/<str:lang_code>/',TranslationsView.as_view(),name='translations'),
    path('convert/',ConvertPriceView.as_view(),name='convert-price'),
]
