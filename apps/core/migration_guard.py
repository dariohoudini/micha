"""
apps/core/migration_guard.py

Pre-flight check for risky migrations against high-value tables.

What counts as risky:
  • RemoveField on a protected table — irreversibly destroys data
  • DeleteModel on a protected table — same, but for the whole table
  • RenameField on a protected table — old code reading old name breaks
    instantly at deploy; needs a multi-step rollout (add new + dual-write
    + backfill + cut over + remove old).
  • AlterField that changes the column type or drops NOT NULL on a
    protected table — can rewrite the whole table under an exclusive
    lock, freezing prod for minutes.

Protected tables are the ledger-of-truth ones where data loss is
unrecoverable: orders, payments, ledger, gift_cards, accounts.

How the guard works:
  • Hooks into the ``pre_migrate`` signal.
  • Walks the migration plan, flags risky ops on protected app_labels.
  • Refuses to proceed unless one of these escape hatches is present:
      - settings.MIGRATION_UNSAFE_ALLOWED is truthy, OR
      - env var MIGRATION_UNSAFE_ALLOWED=1, OR
      - the migration file itself declares ``unsafe_allowed = True`` at
        module scope — operator-acknowledged per-migration.
  • The refusal is a hard ``CommandError`` — migrate aborts, no DDL runs.

This is a guard rail, not a fence. The point is to force a deliberate
pause and an explicit acknowledgement, not to block all schema change.
"""
from __future__ import annotations

import os
import logging

from django.core.management.base import CommandError
from django.db.migrations.operations import (
    RemoveField, DeleteModel, RenameField, AlterField,
)


log = logging.getLogger(__name__)


PROTECTED_APPS = frozenset({
    'orders',
    'payments',
    'ledger',
    'gift_cards',
    'accounts',
})


def _is_unsafe_allowed(migration) -> bool:
    """Per-migration opt-in via module-level ``unsafe_allowed = True``.

    Lets a single, reviewed migration override the guard without
    leaving global blanket escape hatches on the operator's shell."""
    return bool(getattr(migration, 'unsafe_allowed', False))


def _global_unsafe_allowed() -> bool:
    """Global escape hatch — settings flag or env var."""
    try:
        from django.conf import settings
        if getattr(settings, 'MIGRATION_UNSAFE_ALLOWED', False):
            return True
    except Exception:
        pass
    return os.environ.get('MIGRATION_UNSAFE_ALLOWED', '') in ('1', 'true', 'yes')


def _is_alter_risky(op) -> bool:
    """Heuristic: AlterField is risky if the column type changes or NOT
    NULL is removed. We can't always tell statically (the model may
    have shifted under us), so be conservative — any AlterField on a
    protected table is treated as risky and needs explicit ack."""
    return isinstance(op, AlterField)


def check_migration(migration):
    """Inspect a single migration object; return a list of risk messages.
    Empty list = safe."""
    app_label = getattr(migration, 'app_label', None)
    if not app_label or app_label not in PROTECTED_APPS:
        return []

    risks = []
    for op in getattr(migration, 'operations', []):
        if isinstance(op, RemoveField):
            risks.append(
                f'{app_label}.{migration.name}: RemoveField '
                f'{op.model_name}.{op.name} — IRREVERSIBLE data loss'
            )
        elif isinstance(op, DeleteModel):
            risks.append(
                f'{app_label}.{migration.name}: DeleteModel '
                f'{op.name} — IRREVERSIBLE table drop'
            )
        elif isinstance(op, RenameField):
            risks.append(
                f'{app_label}.{migration.name}: RenameField '
                f'{op.model_name}.{op.old_name} → {op.new_name} — '
                f'old code reading the old name will crash at deploy. '
                f'Use a 4-step rollout (add new + dual-write + backfill '
                f'+ cut over + remove old) instead.'
            )
        elif _is_alter_risky(op):
            risks.append(
                f'{app_label}.{migration.name}: AlterField '
                f'{op.model_name}.{op.name} — may rewrite the whole '
                f'table under an exclusive lock. Verify safety on '
                f'production-sized data, then ack with unsafe_allowed.'
            )
    return risks


def guard_migration_plan(plan):
    """Walk a Django migration plan, raise CommandError on risk.

    ``plan`` is the iterable yielded by ``MigrationExecutor.migration_plan``:
    each item is ``(migration, backwards: bool)``.
    """
    if _global_unsafe_allowed():
        log.warning('migration_guard: global escape hatch active — '
                    'risky operations on protected tables will NOT be blocked')
        return

    all_risks = []
    for migration, backwards in plan:
        if backwards:
            # Backwards migrations are usually data-restorative or
            # admin-driven. We don't second-guess them here.
            continue
        if _is_unsafe_allowed(migration):
            log.info('migration_guard: %s.%s has unsafe_allowed=True — '
                     'risky ops permitted', migration.app_label, migration.name)
            continue
        risks = check_migration(migration)
        if risks:
            all_risks.extend(risks)

    if all_risks:
        body = '\n  • '.join(all_risks)
        raise CommandError(
            'migration_guard: refusing to run risky migrations on '
            f'protected tables (apps: {", ".join(sorted(PROTECTED_APPS))}).\n\n'
            f'  • {body}\n\n'
            'To proceed, either:\n'
            '  (a) add ``unsafe_allowed = True`` at the top of the migration '
            'file (per-migration ack), or\n'
            '  (b) set MIGRATION_UNSAFE_ALLOWED=1 in the environment '
            '(one-shot global override).\n'
        )
