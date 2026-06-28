"""
Audit-trail tamper-evidence regression (Audit/Compliance/SLA doc CH8).

AdminActionLog is the central who-did-what admin trail. Before this it was
"immutable" by docstring only. These tests lock the CH8 guarantees:

  - every row is hash-chained (seq increments, prev_hash links, entry_hash set);
  - the chain verifies end-to-end while intact;
  - altering a past row's CONTENT is detected (entry_hash mismatch);
  - deleting a past row is detected (sequence gap);
  - the trail is genuinely append-only (re-save and .delete() are rejected);
  - the verification task pages (CRITICAL) + sets the gauge to 0 on a break.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.admin_actions.models import AdminActionLog
from apps.core.audit_chain import verify_chain

User = get_user_model()


def _mk(admin, action='ban_user', **kw):
    return AdminActionLog.objects.create(
        admin=admin, action=action,
        target_type=kw.pop('target_type', 'user'),
        target_id=kw.pop('target_id', '42'),
        note=kw.pop('note', ''),
        metadata=kw.pop('metadata', {}),
        **kw,
    )


class AuditChainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email='admin@micha.test', password='x', username='adm')

    def _all(self):
        return AdminActionLog.objects.filter(seq__isnull=False).order_by('seq')

    def test_rows_are_hash_chained(self):
        a = _mk(self.admin, note='first')
        b = _mk(self.admin, note='second')
        c = _mk(self.admin, note='third')
        self.assertEqual([a.seq, b.seq, c.seq], [1, 2, 3])
        # Genesis row links to empty; each row links to its predecessor's hash.
        self.assertEqual(a.prev_hash, '')
        self.assertTrue(a.entry_hash.startswith('sha256:'))
        self.assertEqual(b.prev_hash, a.entry_hash)
        self.assertEqual(c.prev_hash, b.entry_hash)

    def test_intact_chain_verifies(self):
        for i in range(5):
            _mk(self.admin, note=f'row{i}')
        result = verify_chain(self._all())
        self.assertTrue(result['ok'])
        self.assertEqual(result['count'], 5)

    def test_content_tampering_is_detected(self):
        _mk(self.admin, note='clean-1')
        victim = _mk(self.admin, note='original')
        _mk(self.admin, note='clean-3')
        # Bypass the append-only save() guard with a raw UPDATE — exactly what
        # a malicious DBA would do. The stored entry_hash no longer matches the
        # (now altered) content.
        AdminActionLog.objects.filter(pk=victim.pk).update(note='doctored')
        result = verify_chain(self._all())
        self.assertFalse(result['ok'])
        self.assertEqual(result['broken_at'], victim.seq)
        self.assertIn('altered', result['reason'])

    def test_deletion_is_detected_as_sequence_gap(self):
        _mk(self.admin, note='a')
        victim = _mk(self.admin, note='b')
        _mk(self.admin, note='c')
        # Bypass the model delete() guard with a queryset delete (raw SQL path).
        AdminActionLog.objects.filter(pk=victim.pk).delete()
        result = verify_chain(self._all())
        self.assertFalse(result['ok'])
        self.assertIn('sequence gap', result['reason'])

    def test_append_only_save_guard(self):
        row = _mk(self.admin, note='locked')
        row.note = 'tampered'
        with self.assertRaises(ValueError):
            row.save()

    def test_append_only_delete_guard(self):
        row = _mk(self.admin, note='permanent')
        with self.assertRaises(ValueError):
            row.delete()


class AuditChainVerifyTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email='admin2@micha.test', password='x', username='adm2')

    def test_task_reports_ok_and_sets_gauge(self):
        from apps.admin_actions.tasks import verify_admin_action_chain
        _mk(self.admin)
        _mk(self.admin)
        result = verify_admin_action_chain()
        self.assertTrue(result['ok'])
        from apps.telemetry.metrics import audit_chain_intact, audit_chain_length
        self.assertEqual(audit_chain_intact.labels(log='admin_action')._value.get(), 1)
        self.assertEqual(audit_chain_length.labels(log='admin_action')._value.get(), 2)

    def test_task_pages_critical_on_broken_chain(self):
        from apps.admin_actions.tasks import verify_admin_action_chain
        _mk(self.admin, note='a')
        victim = _mk(self.admin, note='b')
        _mk(self.admin, note='c')
        AdminActionLog.objects.filter(pk=victim.pk).update(note='doctored')

        with self.assertLogs('audit', level='CRITICAL') as cm:
            result = verify_admin_action_chain()

        self.assertFalse(result['ok'])
        self.assertTrue(any('audit.chain_broken' in m for m in cm.output))
        from apps.telemetry.metrics import audit_chain_intact
        self.assertEqual(audit_chain_intact.labels(log='admin_action')._value.get(), 0)
