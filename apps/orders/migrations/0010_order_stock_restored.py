# Generated for stock_restore primitive — idempotency anchor for
# payment-fail / abandoned-checkout / manual-cancel restock unwind.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0009_returnrequest_returnevent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='stock_restored',
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name='order',
            name='stock_restored_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='stock_restored_source',
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
