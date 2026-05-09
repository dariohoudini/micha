"""
Add the search_vector column + GIN index + unaccent extension.

The extension creation is wrapped so this migration is safe to run on
SQLite (dev) — it just no-ops there. The GIN index uses RunSQL guarded
by a vendor check.
"""
import django.contrib.postgres.search
from django.contrib.postgres.operations import UnaccentExtension
from django.db import connection, migrations


def _create_gin_index(apps, schema_editor):
    if connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            'CREATE INDEX IF NOT EXISTS products_product_search_vector_gin '
            'ON products_product USING GIN (search_vector)'
        )


def _drop_gin_index(apps, schema_editor):
    if connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute('DROP INDEX IF EXISTS products_product_search_vector_gin')


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0009_pricetier'),
    ]

    operations = [
        # Postgres unaccent extension. Safe no-op on non-Postgres; does
        # nothing if the extension is already installed.
        UnaccentExtension(),

        migrations.AddField(
            model_name='product',
            name='search_vector',
            field=django.contrib.postgres.search.SearchVectorField(blank=True, null=True),
        ),

        migrations.RunPython(_create_gin_index, reverse_code=_drop_gin_index),
    ]
