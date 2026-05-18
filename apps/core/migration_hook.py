"""
Wire ``apps/core/migration_guard.guard_migration_plan`` into Django's
migrate command by monkey-patching MigrationExecutor.migrate.

We patch ``migrate`` rather than ``migration_plan`` so the guard runs
*after* the plan is computed but *before* any DDL is executed. By that
point ``executor.migrate(targets, plan=plan)`` is the entry point that
actually runs the operations.

Using ``pre_migrate`` signal instead would be too late — pre_migrate
fires once per app_label inside the run, and aborting mid-run leaves
partial schema state.
"""
from __future__ import annotations

import logging

from django.db.migrations.executor import MigrationExecutor


log = logging.getLogger(__name__)


_ORIGINAL_MIGRATE = MigrationExecutor.migrate
_PATCHED_FLAG = '_micha_migration_guard_patched'


def _patched_migrate(self, targets, plan=None, state=None, fake=False,
                     fake_initial=False):
    if plan is None:
        plan = self.migration_plan(targets)
    # Run the guard. Raises CommandError on risk; we let it propagate
    # so manage.py prints the error and exits non-zero.
    try:
        from .migration_guard import guard_migration_plan
        guard_migration_plan(plan)
    except ImportError:
        log.exception('migration_guard import failed — proceeding without guard')
    return _ORIGINAL_MIGRATE(
        self, targets, plan=plan, state=state, fake=fake,
        fake_initial=fake_initial,
    )


if not getattr(MigrationExecutor, _PATCHED_FLAG, False):
    MigrationExecutor.migrate = _patched_migrate
    setattr(MigrationExecutor, _PATCHED_FLAG, True)
