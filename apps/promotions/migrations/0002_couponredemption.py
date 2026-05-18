# Generated for coupon redemption ledger

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('promotions', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CouponRedemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_id', models.CharField(max_length=80)),
                ('applied_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('subtotal_at_apply', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('status', models.CharField(choices=[('applied', 'Applied'), ('released', 'Released')], default='applied', max_length=12)),
                ('applied_at', models.DateTimeField(auto_now_add=True)),
                ('released_at', models.DateTimeField(blank=True, null=True)),
                ('note', models.CharField(blank=True, max_length=200)),
                ('coupon', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='redemptions', to='promotions.coupon')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coupon_redemptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [
                    models.Index(fields=['user', 'coupon'], name='promotions__user_id_coup_idx'),
                    models.Index(fields=['status', 'applied_at'], name='promotions__status__app_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=['coupon', 'order_id'], name='uniq_coupon_redemption_per_order'),
                ],
            },
        ),
    ]
