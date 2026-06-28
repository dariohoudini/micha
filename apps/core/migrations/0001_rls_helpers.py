"""
RLS helper functions (Security & RLS doc Part 1 CH8).

Creates the STABLE PostgreSQL functions the RLS policies read the tenant
context through (current_tenant_user / current_tenant_seller /
current_tenant_courier / current_role_is). PostgreSQL-only: a no-op on
SQLite (dev) and any non-PostgreSQL backend, so the dev DB and the test
suite are unaffected. Enabling RLS on individual protected tables is a
separate, staged, reviewed migration per table (CH11 rollout safety) that
depends on these helpers.
"""
from django.db import migrations

from apps.core import rls


def create_helpers(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(rls.helper_functions_sql())


def drop_helpers(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(rls.drop_helper_functions_sql())


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.RunPython(create_helpers, drop_helpers),
    ]
