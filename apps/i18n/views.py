from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers
from .models import Currency, Language, Translation

class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model=Currency
        fields=['code','name','symbol','exchange_rate_to_aoa']

class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model=Language
        fields=['code','name','native_name','is_rtl']

class CurrencyListView(generics.ListAPIView):
    serializer_class=CurrencySerializer
    permission_classes=[permissions.AllowAny]
    queryset=Currency.objects.filter(is_active=True)

class LanguageListView(generics.ListAPIView):
    serializer_class=LanguageSerializer
    permission_classes=[permissions.AllowAny]
    queryset=Language.objects.filter(is_active=True)

class TranslationsView(APIView):
    permission_classes=[permissions.AllowAny]
    def get(self,request,lang_code):
        try:
            lang=Language.objects.get(code=lang_code,is_active=True)
            translations={t.key:t.value for t in Translation.objects.filter(language=lang)}
            return Response({'language':lang_code,'translations':translations})
        except Language.DoesNotExist:
            return Response({"detail":"Language not found."},status=404)

class ConvertPriceView(APIView):
    permission_classes=[permissions.AllowAny]
    def get(self,request):
        amount=float(request.query_params.get('amount',0))
        from_currency=request.query_params.get('from','AOA')
        to_currency=request.query_params.get('to','USD')
        try:
            from_cur=Currency.objects.get(code=from_currency)
            to_cur=Currency.objects.get(code=to_currency)
            amount_in_aoa=amount/float(from_cur.exchange_rate_to_aoa)
            converted=amount_in_aoa*float(to_cur.exchange_rate_to_aoa)
            return Response({'from':from_currency,'to':to_currency,'amount':amount,'converted':round(converted,2),'rate':float(to_cur.exchange_rate_to_aoa)})
        except Currency.DoesNotExist:
            return Response({"detail":"Currency not found."},status=404)
