"""
Gap-Coverage CH7 — hash-chain tamper-evidence on the financial journal.

Locks the close: JournalEntry is sealed into the chain at posting time,
the chain verifies end-to-end, and any alteration / deletion / insertion
of a historical money entry is detected at the exact sequence number.
Mirrors apps/admin_actions/tests_audit_chain.py (the admin-trail lock).
"""
from datetime import date

from django.test import TestCase

from apps.core.audit_chain import verify_chain
from apps.accounting.models import GLAccount, JournalEntry
from apps.accounting import services


class JournalChainTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # The chart-of-accounts migration seeds 1000/2000 — tolerate both.
        GLAccount.objects.get_or_create(
            code='1000', defaults=dict(name='Cash', account_type='asset',
                                       normal_balance='debit'))
        GLAccount.objects.get_or_create(
            code='2000', defaults=dict(name='Escrow Liability',
                                       account_type='liability',
                                       normal_balance='credit'))

    @staticmethod
    def _post(n=1, cents=500):
        entries = []
        for i in range(n):
            entries.append(services.post_journal(
                entry_date=date.today(),
                description=f'chain test {i}',
                lines=[{'account': '1000', 'debit': cents},
                       {'account': '2000', 'credit': cents}]))
        return entries

    @staticmethod
    def _all():
        return list(JournalEntry.objects.filter(seq__isnull=False)
                    .order_by('seq').prefetch_related('lines'))

    def test_post_journal_seals_the_chain(self):
        e1, e2, e3 = self._post(3)
        self.assertEqual([e1.seq, e2.seq, e3.seq], [1, 2, 3])
        self.assertEqual(e1.prev_hash, '')
        self.assertEqual(e2.prev_hash, e1.entry_hash)
        self.assertEqual(e3.prev_hash, e2.entry_hash)
        self.assertTrue(e1.entry_hash.startswith('sha256:'))

    def test_intact_chain_verifies(self):
        self._post(3)
        result = verify_chain(self._all())
        self.assertTrue(result['ok'])
        self.assertEqual(result['count'], 3)

    def test_altered_money_content_is_detected(self):
        e1, _, _ = self._post(3)
        # Tamper via queryset update — bypasses save(), like a privileged
        # actor or bug with raw write access would.
        JournalEntry.objects.filter(pk=e1.pk).update(total_cents=999999)
        result = verify_chain(self._all())
        self.assertFalse(result['ok'])
        self.assertEqual(result['broken_at'], 1)
        self.assertIn('altered', result['reason'])

    def test_altered_line_is_detected(self):
        # The lines carry the actual debits/credits — they must be inside
        # the integrity envelope, not just the entry header.
        e1, _, _ = self._post(3)
        line = e1.lines.order_by('pk').first()
        type(line).objects.filter(pk=line.pk).update(debit_cents=1)
        result = verify_chain(self._all())
        self.assertFalse(result['ok'])
        self.assertEqual(result['broken_at'], 1)

    def test_deleted_entry_is_detected(self):
        _, e2, _ = self._post(3)
        e2.lines.all().delete()
        JournalEntry.objects.filter(pk=e2.pk).delete()
        result = verify_chain(self._all())
        self.assertFalse(result['ok'])
        self.assertEqual(result['broken_at'], 3)   # gap where seq 2 was

    def test_verification_task_reports_break(self):
        from apps.accounting.tasks import verify_journal_chain
        e1, _ = self._post(2)
        self.assertTrue(verify_journal_chain()['ok'])
        JournalEntry.objects.filter(pk=e1.pk).update(description='forged')
        result = verify_journal_chain()
        self.assertFalse(result['ok'])
        self.assertEqual(result['broken_at'], 1)
