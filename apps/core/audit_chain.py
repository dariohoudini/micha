"""
Hash-chain tamper-evidence for audit trails (Audit/Compliance/SLA doc CH8).

An append-only table proves nothing on its own: a DBA, an attacker with DB
access, or a well-meaning admin can still UPDATE or DELETE a row to hide what
happened — and a trail that can be silently altered is not evidence. Hash-
chaining makes any such alteration *detectable*. Each record stores the hash
of the previous record plus a hash of its own content, so the records form a
chain:

    record[n].entry_hash = SHA256(record[n].content + record[n-1].entry_hash)

Altering a past record changes its hash and breaks every link after it;
deleting or inserting a record breaks the monotonic sequence; and a routine
verification job (re-walking the chain) catches the break and pages on-call.
This is the difference between "a log" and "evidence" — CH8 Level 2 (tamper-
EVIDENT). It does not PREVENT a privileged write, but it guarantees the write
is DETECTED, which is what makes the trail trustworthy.

This module is deliberately model-agnostic so any audit table can adopt the
chain: a record just needs ``seq``, ``prev_hash``, ``entry_hash`` and a
``chain_payload()`` returning the canonical dict that was hashed.
"""
import hashlib
import json


def compute_entry_hash(payload: dict, prev_hash: str) -> str:
    """Deterministic SHA-256 over the canonical record content, chained to the
    previous record's hash.

    ``sort_keys`` + compact separators make the serialization stable across
    dict insertion order and Python versions, so verification recomputes the
    exact same digest years later. ``default=str`` lets non-JSON-native values
    (Decimal, datetime already isoformatted by the caller) serialize safely.
    """
    body = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    digest = hashlib.sha256(f'{prev_hash}\n{body}'.encode('utf-8')).hexdigest()
    return f'sha256:{digest}'


def verify_chain(records) -> dict:
    """Re-walk an ordered (seq ascending) iterable of chained records and
    confirm the chain is intact.

    Each record must expose ``.seq``, ``.prev_hash``, ``.entry_hash`` and a
    ``.chain_payload()`` method. Returns a result dict::

        {'ok': bool, 'count': int, 'broken_at': seq|None, 'reason': str}

    ``ok=False`` is returned on the FIRST anomaly, with ``broken_at`` set to
    the sequence number where the chain failed and ``reason`` describing it:
      - a content alteration  -> entry_hash mismatch
      - a deleted/inserted row -> sequence gap
      - a relinked record      -> prev_hash mismatch
    """
    prev_hash = ''
    expected_seq = None
    count = 0
    for r in records:
        count += 1
        if expected_seq is not None and r.seq != expected_seq:
            return {
                'ok': False, 'count': count, 'broken_at': r.seq,
                'reason': (f'sequence gap: expected {expected_seq}, got {r.seq} '
                           f'(a record was deleted or inserted)'),
            }
        if r.prev_hash != prev_hash:
            return {
                'ok': False, 'count': count, 'broken_at': r.seq,
                'reason': 'prev_hash mismatch (chain link broken)',
            }
        recomputed = compute_entry_hash(r.chain_payload(), r.prev_hash)
        if recomputed != r.entry_hash:
            return {
                'ok': False, 'count': count, 'broken_at': r.seq,
                'reason': 'entry_hash mismatch (record content was altered)',
            }
        prev_hash = r.entry_hash
        expected_seq = r.seq + 1
    return {'ok': True, 'count': count, 'broken_at': None, 'reason': ''}
