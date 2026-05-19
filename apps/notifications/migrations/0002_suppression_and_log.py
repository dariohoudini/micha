# Generated for SuppressedEmail + NotificationLog

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SuppressedEmail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(db_index=True, max_length=254, unique=True)),
                ('reason', models.CharField(help_text='unsubscribe | hard_bounce | spam_complaint | manual', max_length=80)),
                ('source', models.CharField(blank=True, help_text='admin / webhook / unsubscribe_link / bounce_handler', max_length=40)),
                ('suppressed_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('note', models.CharField(blank=True, max_length=200)),
            ],
            options={
                'ordering': ['-suppressed_at'],
                'indexes': [
                    models.Index(fields=['reason', '-suppressed_at'], name='notifs_supp_reason_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='NotificationLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('category', models.CharField(db_index=True, max_length=40)),
                ('channel', models.CharField(default='email', max_length=10)),
                ('sent', models.BooleanField(db_index=True)),
                ('reason', models.CharField(max_length=40)),
                ('subject', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notification_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['user', '-created_at'], name='notifs_log_user_idx'),
                    models.Index(fields=['email', '-created_at'], name='notifs_log_email_idx'),
                    models.Index(fields=['category', 'sent', '-created_at'], name='notifs_log_cat_idx'),
                ],
            },
        ),
    ]
