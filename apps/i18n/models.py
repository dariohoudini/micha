from django.db import models

class Currency(models.Model):
    code = models.CharField(max_length=5, unique=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=5)
    exchange_rate_to_aoa = models.DecimalField(max_digits=12, decimal_places=4, default=1)
    is_active = models.BooleanField(default=True)
    last_updated = models.DateTimeField(auto_now=True)

class Language(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    native_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    is_rtl = models.BooleanField(default=False)

class Translation(models.Model):
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name='translations')
    key = models.CharField(max_length=200)
    value = models.TextField()
    class Meta: unique_together = ('language', 'key')
