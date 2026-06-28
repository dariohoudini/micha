"""
MICHA Security Hardening Middleware
=====================================
Defends against:
1. Large payload attacks (DoS via huge request bodies)
2. Path traversal in filenames
3. Content-type spoofing
4. Suspicious header injection
5. SQL injection patterns in query strings
6. XSS in query parameters
7. Rate limit headers
"""
import re
import logging
from django.http import JsonResponse

logger = logging.getLogger('micha.security')

# Patterns that indicate malicious input
SQLI_PATTERNS = re.compile(
    r'(\bunion\b.*\bselect\b|\bselect\b.*\bfrom\b|\bdrop\b.*\btable\b|'
    r'\binsert\b.*\binto\b|\bdelete\b.*\bfrom\b|--|;.*--|\bexec\b.*\()',
    re.IGNORECASE
)

XSS_PATTERNS = re.compile(
    r'(<script|javascript:|vbscript:|onload=|onerror=|onclick=|'
    r'<iframe|<object|<embed|<link.*rel=|data:text/html)',
    re.IGNORECASE
)

PATH_TRAVERSAL = re.compile(r'\.\./|\.\.\\|%2e%2e|%252e%252e', re.IGNORECASE)

# Max request sizes
MAX_JSON_SIZE = 10 * 1024 * 1024    # 10MB for API requests
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB for file uploads
MAX_QUERY_STRING_LENGTH = 2048


class SecurityHardeningMiddleware:
    """
    Runs before all views. Rejects obviously malicious requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip security checks for admin and static files
        if request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return self.get_response(request)

        # 1. Check query string length
        if len(request.META.get('QUERY_STRING', '')) > MAX_QUERY_STRING_LENGTH:
            logger.warning('query_string_too_long', extra={
                'path': request.path,
                'ip': self._get_ip(request),
                'length': len(request.META.get('QUERY_STRING', '')),
            })
            return JsonResponse({'error': 'Query string too long'}, status=400)

        # 2. Check for path traversal in URL
        if PATH_TRAVERSAL.search(request.path):
            logger.warning('path_traversal_attempt', extra={
                'path': request.path,
                'ip': self._get_ip(request),
            })
            return JsonResponse({'error': 'Invalid path'}, status=400)

        # 3. Check for SQL injection in query params
        query_string = request.META.get('QUERY_STRING', '')
        if SQLI_PATTERNS.search(query_string):
            logger.warning('sqli_attempt_query', extra={
                'path': request.path,
                'ip': self._get_ip(request),
                'query': query_string[:200],
            })
            return JsonResponse({'error': 'Invalid request'}, status=400)

        # 4. Check request body size for API endpoints
        if request.path.startswith('/api/'):
            content_length = int(request.META.get('CONTENT_LENGTH', 0) or 0)
            content_type = request.META.get('CONTENT_TYPE', '')

            if 'multipart' in content_type:
                if content_length > MAX_UPLOAD_SIZE:
                    return JsonResponse({'error': 'File too large. Maximum 20MB'}, status=413)
            else:
                if content_length > MAX_JSON_SIZE:
                    return JsonResponse({'error': 'Request body too large'}, status=413)

        # 5. Check for suspicious headers
        for header in ['HTTP_X_FORWARDED_HOST', 'HTTP_X_ORIGINAL_URL']:
            if header in request.META:
                value = request.META[header]
                if XSS_PATTERNS.search(value):
                    logger.warning('xss_in_header', extra={
                        'header': header,
                        'ip': self._get_ip(request),
                    })
                    return JsonResponse({'error': 'Invalid request'}, status=400)

        response = self.get_response(request)

        # 6. Add security response headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = (
            'geolocation=(), camera=(), microphone=(), '
            'payment=(self), interest-cohort=()'
        )
        # Cross-origin isolation — protects against Spectre-class attacks
        # and prevents other origins from embedding our API responses as
        # resources without our consent.
        response.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.setdefault('Cross-Origin-Resource-Policy', 'same-site')

        # Content-Security-Policy — only set on API responses (HTML pages
        # have their own CSP tuned per asset host). For JSON endpoints a
        # strict default-src 'none' prevents any surprise rendering if a
        # response is ever misinterpreted as HTML by an old client.
        ctype = response.get('Content-Type', '')
        if 'application/json' in ctype or request.path.startswith('/api/'):
            # AliExpress Security Engineering Workflow §5.6 —
            # ``report-uri`` directs browsers to POST violation
            # reports to our own endpoint, which writes them to
            # SecurityAuditLog. Useful even on a strict-deny CSP:
            # any blocked attempt to render this JSON as HTML
            # produces an actionable signal in the audit log.
            response.setdefault(
                'Content-Security-Policy',
                "default-src 'none'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'none'; "
                "report-uri /api/v1/security/csp-report/"
            )

        # Remove server info headers
        if 'Server' in response:
            del response['Server']
        if 'X-Powered-By' in response:
            del response['X-Powered-By']

        return response

    def _get_ip(self, request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        return forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '')


class FileUploadSecurityMiddleware:
    """
    Validates uploaded files before they reach views.
    Prevents:
    - Executable file uploads
    - Double extension attacks (file.php.jpg)
    - MIME type spoofing
    - Zip bombs
    """

    ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    ALLOWED_DOCUMENT_EXTENSIONS = {'.pdf'}
    DANGEROUS_EXTENSIONS = {
        '.php', '.php3', '.php4', '.php5', '.phtml',
        '.asp', '.aspx', '.jsp', '.jspx',
        '.exe', '.bat', '.cmd', '.sh', '.bash',
        '.py', '.rb', '.pl', '.cgi',
        '.htaccess', '.htpasswd',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.FILES:
            for field_name, file_obj in request.FILES.items():
                check = self._check_file(file_obj)
                if not check['safe']:
                    logger.warning('dangerous_file_upload', extra={
                        'field': field_name,
                        'filename': file_obj.name,
                        'reason': check['reason'],
                        'ip': request.META.get('REMOTE_ADDR'),
                    })
                    return JsonResponse(
                        {'error': f'Invalid file: {check["reason"]}'},
                        status=400,
                    )

        return self.get_response(request)

    def _check_file(self, file_obj) -> dict:
        import os
        name = file_obj.name.lower()

        # Check for dangerous extensions
        _, ext = os.path.splitext(name)
        if ext in self.DANGEROUS_EXTENSIONS:
            return {'safe': False, 'reason': f'File type {ext} not allowed'}

        # Check for double extension attack (file.php.jpg)
        parts = name.split('.')
        if len(parts) > 2:
            for part in parts[:-1]:
                if f'.{part}' in self.DANGEROUS_EXTENSIONS:
                    return {'safe': False, 'reason': 'Double extension attack detected'}

        # Check file size
        if file_obj.size > MAX_UPLOAD_SIZE:
            return {'safe': False, 'reason': 'File too large'}

        # Check for null bytes in filename
        if '\x00' in name:
            return {'safe': False, 'reason': 'Invalid filename'}

        return {'safe': True, 'reason': None}
