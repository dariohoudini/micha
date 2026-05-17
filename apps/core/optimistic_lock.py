"""
apps/core/optimistic_lock.py

Optimistic-concurrency helper. Pattern: each row carries a monotonic
``version`` integer. Writers send the version they read with; the
update only succeeds if the version still matches. If two admins read
the same row, the second to save sees a stale-version error and is
forced to refresh.

Why this matters: classical lost-update bug. Two admins open a product
in the admin UI; A changes price, B changes description; both click
Save. Without optimistic locking, whichever saves last silently wipes
the other's change. With it, the second save fails with a clear error;
the admin reloads, sees the merged state, makes their change against
the fresh view.

Usage:
    class Product(OptimisticLockedMixin, models.Model):
        # ... existing fields ...
        version = models.PositiveIntegerField(default=0)

    # In a view:
    instance = update_with_version(
        Product, pk=request.data['id'],
        expected_version=int(request.data['version']),
        updates={'price': Decimal('9.99')},
    )
    # → returns the saved instance, version+1
    # → raises StaleVersion on conflict

Built on UPDATE...WHERE version=... so the check is atomic without
needing SELECT FOR UPDATE. Works in one round-trip.
"""
from __future__ import annotations
from django.db import models, transaction


class StaleVersion(Exception):
    """The row's version moved between read and write. Caller should
    refetch and retry."""
    def __init__(self, model: str, pk, expected: int, current=None):
        self.model = model
        self.pk = pk
        self.expected = expected
        self.current = current
        msg = (f'{model}#{pk} version moved: expected {expected}, '
               f'found {"missing" if current is None else current}')
        super().__init__(msg)


class OptimisticLockedMixin:
    """Adds save_with_version() to any model with a ``version`` field.

    Note: regular ``save()`` is unaffected — admins who explicitly want
    last-writer-wins still get that behaviour. The mixin is opt-in per
    call site so we don't break existing code.
    """
    def save_with_version(self, *, expected_version: int, update_fields=None):
        """Atomic compare-and-set. Increments version on success."""
        cls = type(self)
        if self.pk is None:
            # First insert — version starts at 0 (or whatever the caller set)
            self.save()
            return self

        # Use F() to bump version in the same statement
        new_version = expected_version + 1
        updates = {'version': new_version}
        if update_fields is None:
            # Save all updatable fields. Default-Django save would do this
            # via INSERT/UPDATE; we mimic via dict comprehension over the
            # instance's fields excluding pk + version.
            for f in cls._meta.fields:
                if f.name in ('id', 'pk', 'version'):
                    continue
                if f.auto_created:
                    continue
                updates[f.attname] = getattr(self, f.attname)
        else:
            for name in update_fields:
                updates[name] = getattr(self, name)

        updated = cls.objects.filter(
            pk=self.pk, version=expected_version,
        ).update(**updates)
        if updated == 0:
            # Either the row is gone OR its version moved. Distinguish for
            # better error reporting.
            current = cls.objects.filter(pk=self.pk).values_list(
                'version', flat=True,
            ).first()
            raise StaleVersion(cls.__name__, self.pk, expected_version, current)
        self.version = new_version
        return self


def update_with_version(model_cls, *, pk, expected_version: int,
                        updates: dict):
    """Functional shorthand for callers that don't want to wire up the
    mixin or instantiate. ``updates`` is the dict of field-name → value
    to set; version is incremented automatically."""
    new_version = expected_version + 1
    payload = dict(updates)
    payload['version'] = new_version
    updated = model_cls.objects.filter(
        pk=pk, version=expected_version,
    ).update(**payload)
    if updated == 0:
        current = model_cls.objects.filter(pk=pk).values_list(
            'version', flat=True,
        ).first()
        raise StaleVersion(model_cls.__name__, pk, expected_version, current)
    return model_cls.objects.get(pk=pk)
