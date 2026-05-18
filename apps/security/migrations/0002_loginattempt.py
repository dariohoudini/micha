# Generated for LoginAttempt audit table

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoginAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.CharField(db_index=True, max_length=255)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=400)),
                ('succeeded', models.BooleanField()),
                ('failure_reason', models.CharField(blank=True, choices=[
                    ('bad_credentials', 'Bad credentials'),
                    ('email_not_verified', 'Email not verified'),
                    ('account_suspended', 'Account suspended'),
                    ('account_locked', 'Account locked (too many failures)'),
                    ('ip_locked', 'IP locked (credential stuffing)'),
                    ('bad_2fa', '2FA code rejected'),
                    ('missing_2fa', '2FA code not provided'),
                    ('unknown', 'Unknown'),
                ], max_length=24)),
                ('triggered_lockout', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['email', '-created_at'], name='security_lo_email_c2f7c5_idx'),
                    models.Index(fields=['ip', '-created_at'], name='security_lo_ip_3e9c79_idx'),
                    models.Index(
                        condition=models.Q(triggered_lockout=True),
                        fields=['triggered_lockout', '-created_at'],
                        name='security_la_locks_idx',
                    ),
                ],
            },
        ),
    ]
