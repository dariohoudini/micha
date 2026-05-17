"""
apps/users/anchor.py

The "deleted user anchor" — a singleton placeholder User row that orphaned
references get reanchored to when a real user is hard-deleted.

The problem this solves:
  Several models (ReturnRequest.buyer, Refund.requested_by, Review.reviewer,
  ProductReview.author, HelpfulVote.user, ReviewFlag.flagged_by) declare
  ON DELETE CASCADE on their user FK. If an admin hard-deletes a real
  user, every one of those rows is silently deleted — including financial
  records (Refund) and audit trails (Review). That's data loss masquerading
  as "deletion".

The fix without a schema migration:
  Before deleting the user, REASSIGN their CASCADE-FK rows to the anchor
  via raw UPDATE. The user is then "leaf-free" and can be deleted
  without cascade taking their orders + reviews with them.

  safe_delete_user(user, actor) does this end-to-end. It's the only
  legitimate way to hard-delete a user; admin UI / cleanup scripts
  should call it.

The anchor itself:
  email = 'deleted-user@anchor.micha' (sentinel)
  is_active = False
  is_deleted = True
  Created on first call to get_anchor() — idempotent.

Why this beats just "set CASCADE FKs to SET_NULL":
  • No schema migration needed (zero downtime to roll out)
  • Reviews / refunds keep a non-null author for audit queries
  • Aggregations like "reviews by user X" still work — they just
    return the anchor for deleted users (which an admin filter can
    exclude)
"""
from django.contrib.auth import get_user_model

ANCHOR_EMAIL = 'deleted-user@anchor.micha'


def get_anchor():
    """Return the singleton anchor User. Created on first call."""
    User = get_user_model()
    anchor = User.objects.filter(email=ANCHOR_EMAIL).first()
    if anchor is not None:
        return anchor
    # Create with minimum viable fields. Set is_active=False so the
    # anchor can never log in.
    return User.objects.create(
        email=ANCHOR_EMAIL,
        is_active=False,
        is_deleted=True,
        password='!unusable!',  # Django marks this as unusable
    )


def safe_delete_user(user, *, actor=None,
                     cascade_relations: set | None = None) -> dict:
    """Reanchor ALL non-CASCADE FK references on this user to the anchor,
    then delete the user row. Per-user-private relations (Cart, Wishlist,
    PointsTransaction, 2FA, idempotency keys, alerts, dev keys, etc.)
    keep their CASCADE behaviour — they belong to the user identity and
    have no sensible meaning on the anchor.

    The ONLY legitimate way to hard-delete a user. Admin UI and cleanup
    scripts must call this; never user.delete() directly.

    Returns:
      {'reanchored': {'app.model.field': row_count, ...},
       'deleted': True, 'anchor_id': N, 'actor_id': M}
    """
    if user is None or user.pk is None:
        return {'reanchored': {}, 'deleted': False}

    anchor = get_anchor()
    if anchor.pk == user.pk:
        return {'error': 'cannot_delete_anchor',
                'reanchored': {}, 'deleted': False}

    User = get_user_model()
    summary = {}

    # Relations that SHOULD cascade with the user — per-user private state
    # whose continued existence on the anchor would be incoherent.
    DEFAULT_CASCADE = {
        'cart.cart.user',
        'wishlist.wishlist.user',
        'loyalty.pointstransaction.user',
        'loyalty.usertier.user',
        'recommendations.productinteraction.user',
        'recommendations.userinterest.user',
        'two_factor.usertotp.user',
        'two_factor.backupcode.user',
        'two_factor.trusteddevice.user',
        'two_factor.challengeattempt.user',
        'idempotency.idempotencykey.user',
        'alerts.savedsearch.user',
        'alerts.alertdelivery.user',
        'dev_keys.apikey.user',
        'dev_keys.apikeyusage.key',  # cascades via APIKey
        'flags.flagoverride.user',
        'shipping.shippingaddress.user',
        'chat.message.sender',
        'gift_cards.giftcard.claimed_by',  # claimed_by is SET_NULL anyway
    }
    cascade_relations = (cascade_relations or set()) | DEFAULT_CASCADE

    # Per-user financial / private state where the FK is PROTECTed at the
    # DB layer AND reanchoring would violate uniqueness on the anchor
    # (e.g. ledger.Account has UNIQUE(type, user) — both victim and anchor
    # already own one of each kind). Explicit delete is the right
    # semantics: a user's private accounts have no meaning after the user
    # is gone.
    EXPLICIT_DELETE = {
        'ledger.account.user',         # per-user store_credit / loyalty
        'ledger.journal.posted_by',    # historical actor — set NULL is OK
    }

    # Walk Django's relation graph: every FK / O2O pointing at User.
    # For each relation: cascade-skip, explicit-delete, or reanchor.
    for rel in User._meta.related_objects:
        try:
            field = rel.field
            related_model = rel.related_model
            field_name = field.name
            rel_key = (f'{related_model._meta.app_label}.'
                       f'{related_model._meta.model_name}.{field_name}')
            if rel_key in cascade_relations:
                continue
            # OneToOne can't fan in — anchor can only hold one such ref.
            if field.one_to_one:
                continue
            if rel_key in EXPLICIT_DELETE:
                if field.null:
                    n = related_model.objects.filter(
                        **{field_name: user}
                    ).update(**{field_name: None})
                else:
                    n, _ = related_model.objects.filter(
                        **{field_name: user}
                    ).delete()
                if n:
                    summary[f'{rel_key} (cleared)'] = n
                continue
            # Default: reanchor to the placeholder. UPDATE works under
            # PROTECT (PROTECT only blocks DELETE).
            n = related_model.objects.filter(
                **{field_name: user}
            ).update(**{field_name: anchor})
            if n:
                summary[rel_key] = n
        except Exception:
            # One relation reanchor failure shouldn't block the others.
            continue

    # Anything still PROTECTED at this point will raise — better that
    # than silent data loss. Operator sees the error and decides.
    user.delete()
    return {'reanchored': summary, 'deleted': True, 'anchor_id': anchor.id,
            'actor_id': getattr(actor, 'id', None)}
