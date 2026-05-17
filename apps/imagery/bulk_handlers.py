"""
apps/imagery/bulk_handlers.py

Bulk-ops handler: re-generate variants for a list of ImageSource IDs.
Useful when:
  • Variant size definitions change and existing variants need refresh
  • A seller wants to bulk re-process their entire catalog
  • Variants got corrupted in storage and need rebuilding

The handler is idempotent — existing variants for each source are
skipped, so re-running is safe.
"""
from apps.bulk_ops.registry import register, BulkHandler


def _bulk_regenerate_variants(item_ref, params, request_user):
    """Re-run variant generation for one ImageSource id."""
    from apps.imagery.models import ImageSource
    from apps.imagery.service import generate_variants_for_source
    try:
        sid = int(item_ref)
    except (TypeError, ValueError):
        raise ValueError(f'bad source id: {item_ref!r}')
    src = ImageSource.objects.filter(pk=sid).first()
    if src is None:
        return {'skipped': True, 'reason': 'source_not_found'}
    summary = generate_variants_for_source(src)
    return summary


register(BulkHandler(
    name='imagery.regenerate_variants',
    fn=_bulk_regenerate_variants,
    audit_action=None,
    description='Re-generate all variants for a list of ImageSource ids.',
))
