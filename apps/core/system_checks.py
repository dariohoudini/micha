"""
apps/core/system_checks.py — extends ``manage.py check`` with project-wide
import-time sanity checks.

Why this exists: in 2026-Q2 a routine audit found seven files across
the codebase that would crash at import time:
  • apps/payments/gateway.py — two indentation errors from a half-
    merged refactor; the entire payments gateway module was
    unimportable. refund_payment + _get_commission_rate dead.
  • apps/payments/tasks.py — undefined ``app`` name; Celery autodiscover
    would crash, no payment-retry workers could start.
  • apps/seller/tasks.py — indentation error inside try block.
  • apps/i18n/views.py — undefined AllowAny; every i18n URL pattern
    would 500 on first request.
  • apps/stores/multi_store_views.py — orphan file with broken refactor.

None of these were caught because:
  • They lived in code paths not exercised in dev.
  • ``manage.py check`` only validates the model layer + admin, not
    arbitrary module imports.
  • Tests covered the happy path of features, not the file-level
    health of cousin modules.

This check walks every .py file in apps/ and attempts to import it.
Any failure surfaces in ``manage.py check`` and (importantly) blocks
``manage.py runserver`` if SILENCED_SYSTEM_CHECKS isn't set.
"""
from __future__ import annotations

import importlib
import os

from django.core.checks import Error, register, Tags


# Orphan duplicate-model files. Importing them would conflict with the
# canonical models. They're not wired into URL routing or admin and
# are scheduled for removal — listed here so the check stays green
# until that cleanup commit lands.
_KNOWN_ORPHAN_MODULES = frozenset({
    'apps.stores.multi_store_models',
    'apps.stores.multi_store_views',
    'apps.promotions.flash_models',
})


def _walk_app_modules(apps_dir: str):
    """Yield importable module dotted-paths for every .py file under
    ``apps_dir``, excluding migrations, tests, and __pycache__."""
    for root, dirs, files in os.walk(apps_dir):
        # Don't recurse into junk directories.
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'migrations')]
        for f in files:
            if not f.endswith('.py'):
                continue
            if f == '__init__.py':
                continue
            # Heuristic test-file exclusion. Tests can do weird things
            # at module level (skip patterns, conditional imports).
            if f.startswith('test_') or f == 'tests.py':
                continue
            if '/tests/' in root:
                continue
            rel = os.path.relpath(os.path.join(root, f), start='.')
            if rel.endswith('.py'):
                rel = rel[:-3]
            dotted = rel.replace(os.sep, '.')
            if dotted in _KNOWN_ORPHAN_MODULES:
                continue
            yield dotted


@register(Tags.compatibility)
def check_apps_modules_import(app_configs, **kwargs):
    """System check: every .py file under apps/ must import cleanly.

    Catches the class of bug where a file has a syntax / NameError that
    silently slips past testing because the file isn't on a hot code
    path — but would crash if a future change pulled it in.
    """
    errors = []
    base = os.path.join(os.path.dirname(__file__), '..', '..', 'apps')
    base = os.path.normpath(base)
    if not os.path.isdir(base):
        return []

    # Use the relative 'apps' walk so dotted-name construction works.
    for dotted in _walk_app_modules('apps'):
        try:
            importlib.import_module(dotted)
        except Exception as e:
            errors.append(Error(
                f'Module {dotted} failed to import: '
                f'{type(e).__name__}: {e}',
                hint='This module would crash if hit at runtime. Fix the '
                     'import-time error, or add it to '
                     '_KNOWN_ORPHAN_MODULES in apps/core/system_checks.py '
                     'if it is deliberately dead code being removed.',
                obj=dotted,
                id='core.E001',
            ))
    return errors
