"""Seed the Luanda-origin 18-province zone matrix (doc CH2) on migrate."""
from django.db import migrations


def seed(apps, schema_editor):
    ProvinceZone = apps.get_model('last_mile', 'ProvinceZone')
    from apps.last_mile import provinces as pv
    origin = 'Luanda'
    for dest in pv.PROVINCES:
        zc = pv.SAME_CITY if dest == origin else pv.classify_zone(origin, dest)
        rates = pv.ZONE_RATES[zc]
        ProvinceZone.objects.get_or_create(
            origin_province=origin, destination_province=dest,
            defaults={'zone_class': zc, 'base_rate_cents': rates['base'],
                      'rate_per_kg_cents': rates['per_kg'],
                      'transit_days_min': rates['days'][0],
                      'transit_days_max': rates['days'][1],
                      'cod_available': pv.cod_available(dest)})


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('last_mile', '0001_initial')]
    operations = [migrations.RunPython(seed, unseed)]
