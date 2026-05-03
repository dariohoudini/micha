"""
Security audit command — run before every deployment.
Usage: python manage.py security_check
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Run security audit before deployment'

    def handle(self, *args, **options):
        issues = []
        warnings = []

        # Critical checks
        if settings.DEBUG:
            issues.append('DEBUG=True in production')

        if '*' in settings.ALLOWED_HOSTS:
            issues.append('ALLOWED_HOSTS contains wildcard (*)')

        if len(settings.SECRET_KEY) < 50:
            issues.append(f'SECRET_KEY too short ({len(settings.SECRET_KEY)} chars, need 50+)')

        if getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False):
            issues.append('CORS_ALLOW_ALL_ORIGINS=True allows any domain')

        if not getattr(settings, 'SESSION_COOKIE_SECURE', False):
            issues.append('SESSION_COOKIE_SECURE=False — sessions exposed over HTTP')

        if not getattr(settings, 'CSRF_COOKIE_SECURE', False):
            issues.append('CSRF_COOKIE_SECURE=False — CSRF token exposed over HTTP')

        if not getattr(settings, 'CSRF_COOKIE_HTTPONLY', False):
            issues.append('CSRF_COOKIE_HTTPONLY=False — CSRF token accessible via JS')

        # Warning checks
        if not getattr(settings, 'SECURE_SSL_REDIRECT', False):
            warnings.append('SECURE_SSL_REDIRECT=False — set FORCE_HTTPS=true in production')

        if not getattr(settings, 'SECURE_HSTS_SECONDS', 0):
            warnings.append('SECURE_HSTS_SECONDS=0 — enable HSTS in production')

        if not getattr(settings, 'SECURE_CONTENT_TYPE_NOSNIFF', False):
            warnings.append('SECURE_CONTENT_TYPE_NOSNIFF=False')

        appypay_key = getattr(settings, 'APPYPAY_API_KEY', '')
        if not appypay_key:
            warnings.append('APPYPAY_API_KEY not set — payments in sandbox mode')

        # Report
        self.stdout.write('\n' + '='*50)
        self.stdout.write('MICHA Express Security Audit')
        self.stdout.write('='*50)

        if issues:
            self.stdout.write(self.style.ERROR(f'\n❌ CRITICAL ISSUES ({len(issues)}):'))
            for issue in issues:
                self.stdout.write(self.style.ERROR(f'   • {issue}'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ No critical issues found'))

        if warnings:
            self.stdout.write(self.style.WARNING(f'\n⚠️  WARNINGS ({len(warnings)}):'))
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f'   • {warning}'))

        # Deployment readiness
        self.stdout.write('\n' + '─'*50)
        if not issues:
            self.stdout.write(self.style.SUCCESS('✅ Ready for deployment'))
        else:
            self.stdout.write(self.style.ERROR(f'❌ Fix {len(issues)} critical issue(s) before deploying'))

        self.stdout.write('')
        return '1' if issues else '0'
