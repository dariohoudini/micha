"""
apps/seo/well_known.py
───────────────────────

``/.well-known/`` endpoints for native deep-linking.

iOS Universal Links and Android App Links require BOTH the native app
to declare an Associated Domain AND the web server at that domain to
serve a verification file:

  iOS:     /.well-known/apple-app-site-association   (no .json extension)
           Content-Type MUST be application/json. Bytes are signed
           against the team-bundle pair declared in the app's
           Associated Domains entitlement.

  Android: /.well-known/assetlinks.json
           Content-Type application/json. Contains the package name +
           SHA-256 signing-key fingerprint(s) of the production APK.

If either file is missing or wrong, the OS silently falls back to
opening the URL in Safari/Chrome instead of the app. Result: every
shared link, every email link, every push-deeplink lands on the
website. Zero in-app deep-linking. Visible only by manually opening
the app and checking "the link didn't open me to a page" — easy bug
to miss in QA.

Settings (all optional — placeholders if unset)
─────────────────────────────────────────────────
  IOS_TEAM_ID          Apple Developer Team ID (10 chars)
  IOS_BUNDLE_ID        Bundle identifier, default reads from capacitor.config
  ANDROID_PACKAGE_NAME Package name, default = IOS_BUNDLE_ID
  ANDROID_SHA256_FINGERPRINTS  List of SHA-256 strings (release + debug keys)

When all settings are absent, the endpoints return well-formed empty
JSON (a valid file, just one that lists no apps). That's the right
behaviour during development — a 404 would mean Apple/Google can't
even FETCH the file, complicating debugging. A 200 with empty list
clearly says "domain is wired, just no apps configured yet."
"""
from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET


# ─── Settings helpers ─────────────────────────────────────────────────

def _ios_team_id() -> str:
    return (getattr(settings, 'IOS_TEAM_ID', '') or '').strip()


def _ios_bundle_id() -> str:
    return (getattr(settings, 'IOS_BUNDLE_ID', 'ao.micha.express') or '').strip()


def _android_package_name() -> str:
    return (
        getattr(settings, 'ANDROID_PACKAGE_NAME', '')
        or _ios_bundle_id()
        or ''
    ).strip()


def _android_sha256_fingerprints() -> list:
    val = getattr(settings, 'ANDROID_SHA256_FINGERPRINTS', None) or []
    if isinstance(val, str):
        # Allow comma-separated string for ops convenience.
        return [v.strip() for v in val.split(',') if v.strip()]
    return [str(v).strip() for v in val if str(v).strip()]


# ─── Endpoints ────────────────────────────────────────────────────────

@csrf_exempt
@require_GET
@cache_control(max_age=3600, public=True)
def apple_app_site_association(request):
    """``GET /.well-known/apple-app-site-association``

    Apple validates this on app install + periodically. Aggressively
    cached at the CDN (1h) — content rarely changes (only on a new
    bundle ID or team rotation). Conservative cache header keeps Apple
    from hammering origin.

    Response shape (Apple's v2 format, the only one supported by iOS 14+):

      {
        "applinks": {
          "details": [
            {
              "appIDs": ["TEAM.bundle"],
              "components": [
                { "/": "/product/*" },
                { "/": "/order/*"   },
                ...
              ]
            }
          ]
        }
      }
    """
    team = _ios_team_id()
    bundle = _ios_bundle_id()

    if not team or not bundle:
        # Empty-but-valid shape. Apple is happy; ops sees "domain wired".
        body = {'applinks': {'details': []}}
    else:
        app_id = f'{team}.{bundle}'
        body = {
            'applinks': {
                'details': [
                    {
                        'appIDs': [app_id],
                        'components': _link_components(),
                    },
                ],
            },
            # webcredentials lets iOS surface saved-password autofill
            # on the website — non-essential but harmless.
            'webcredentials': {'apps': [app_id]},
        }

    # Apple requires Content-Type: application/json, no extension on URL.
    return JsonResponse(body)


@csrf_exempt
@require_GET
@cache_control(max_age=3600, public=True)
def assetlinks_json(request):
    """``GET /.well-known/assetlinks.json``

    Google fetches this when a user first taps an http(s) URL with our
    domain. Bytes signed against the SHA-256 fingerprint(s) declared
    here vs. the actual APK signature.

    Multiple fingerprints supported (release + debug + Play App Signing
    upload key). Empty list = no Android App Links binding, OS falls
    back to browser.
    """
    package = _android_package_name()
    fingerprints = _android_sha256_fingerprints()

    if not package or not fingerprints:
        return JsonResponse([], safe=False)

    body = [
        {
            'relation': [
                'delegate_permission/common.handle_all_urls',
            ],
            'target': {
                'namespace': 'android_app',
                'package_name': package,
                'sha256_cert_fingerprints': fingerprints,
            },
        },
    ]
    return JsonResponse(body, safe=False)


# ─── Path components ─────────────────────────────────────────────────

def _link_components() -> list:
    """Path patterns the native app should claim from the browser.

    Order matters in Apple's matcher — first match wins. Use ``"/*"``
    sparingly; here we list each in-app destination explicitly so a
    /blog or /support page stays in the browser.
    """
    return [
        {'/': '/product/*',  'comment': 'Product detail'},
        {'/': '/order/*',    'comment': 'Order detail'},
        {'/': '/orders/*',   'comment': 'Order detail (plural alias)'},
        {'/': '/chat/*',     'comment': 'Chat conversation'},
        {'/': '/store/*',    'comment': 'Store profile'},
        {'/': '/notifications/*', 'comment': 'Notifications inbox'},
        {'/': '/seller/*',   'comment': 'Seller dashboard'},
        # Auth callbacks — OAuth providers redirect here. MUST be
        # claimed so the app picks up the token rather than the browser.
        {'/': '/auth/callback/*', 'comment': 'OAuth callback'},
    ]
