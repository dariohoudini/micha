"""
Property Vertical doc CH11/CH12 — viewing scheduling + offer negotiation.

Locks the two transaction state machines: viewings (requested →
confirmed → completed/no_show, cancel by either party, lister-only
hosting actions) and offers (submitted ↔ countered → accepted/rejected/
withdrawn, alternating turns, chained non-repudiable history, both
parties notified).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from apps.rentals.models import Listing, Offer, Viewing

User = get_user_model()


def _listing(lister, **kw):
    defaults = dict(
        lister=lister, category='property', purpose='sale',
        title='Vivenda T3 Talatona', description='Casa espaçosa',
        price=45000000, status='active', price_negotiable=True,
    )
    defaults.update(kw)
    return Listing.objects.create(**defaults)


class PropertyFlowTestBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='dono@test.ao', password='pw12345678!', username='dono')
        self.buyer = User.objects.create_user(
            email='comprador@test.ao', password='pw12345678!', username='compr')
        self.listing = _listing(self.owner)
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)
        self.buyer_client = APIClient()
        self.buyer_client.force_authenticate(self.buyer)


class ViewingFlowTests(PropertyFlowTestBase):

    def _request_viewing(self):
        when = (timezone.now() + timedelta(days=2)).isoformat()
        return self.buyer_client.post(
            f'/api/v1/rentals/{self.listing.id}/viewings/',
            {'scheduled_at': when, 'note': 'Posso ir de manhã'}, format='json')

    def test_full_viewing_lifecycle(self):
        r = self._request_viewing()
        self.assertEqual(r.status_code, 201)
        vid = r.data['id']
        self.assertEqual(r.data['status'], 'requested')
        # the lister was notified
        self.assertTrue(Notification.objects.filter(
            user=self.owner, data__viewing_id=vid).exists())
        # lister confirms, then completes
        for action, expected in (('confirm', 'confirmed'),
                                 ('complete', 'completed')):
            rr = self.owner_client.post(
                f'/api/v1/rentals/viewings/{vid}/action/',
                {'action': action}, format='json')
            self.assertEqual(rr.status_code, 200)
            self.assertEqual(rr.data['status'], expected)
        # the record survives as the accountability trail
        self.assertTrue(Viewing.objects.filter(pk=vid,
                                               status='completed').exists())

    def test_requester_cannot_confirm_own_request(self):
        vid = self._request_viewing().data['id']
        r = self.buyer_client.post(
            f'/api/v1/rentals/viewings/{vid}/action/',
            {'action': 'confirm'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_either_party_can_cancel(self):
        vid = self._request_viewing().data['id']
        r = self.buyer_client.post(
            f'/api/v1/rentals/viewings/{vid}/action/',
            {'action': 'cancel'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['status'], 'cancelled')

    def test_cannot_view_own_listing_or_past_date(self):
        r = self.owner_client.post(
            f'/api/v1/rentals/{self.listing.id}/viewings/',
            {'scheduled_at': (timezone.now() + timedelta(days=1)).isoformat()},
            format='json')
        self.assertEqual(r.status_code, 400)
        r = self.buyer_client.post(
            f'/api/v1/rentals/{self.listing.id}/viewings/',
            {'scheduled_at': (timezone.now() - timedelta(days=1)).isoformat()},
            format='json')
        self.assertEqual(r.status_code, 400)

    def test_third_party_sees_404(self):
        vid = self._request_viewing().data['id']
        stranger = APIClient()
        stranger.force_authenticate(User.objects.create_user(
            email='x@test.ao', password='pw12345678!', username='x'))
        r = stranger.post(f'/api/v1/rentals/viewings/{vid}/action/',
                          {'action': 'cancel'}, format='json')
        self.assertEqual(r.status_code, 404)


class OfferFlowTests(PropertyFlowTestBase):

    def _submit(self, amount=40000000):
        return self.buyer_client.post(
            f'/api/v1/rentals/{self.listing.id}/offers/',
            {'amount': amount, 'message': 'Proposta inicial'}, format='json')

    def test_negotiation_loop_with_recorded_history(self):
        o1 = self._submit().data
        self.assertEqual(o1['status'], 'submitted')
        # lister counters
        r = self.owner_client.post(
            f"/api/v1/rentals/offers/{o1['id']}/action/",
            {'action': 'counter', 'amount': 43000000}, format='json')
        self.assertEqual(r.status_code, 201)
        o2 = r.data
        self.assertEqual(o2['version'], 2)
        # buyer counters back
        r = self.buyer_client.post(
            f"/api/v1/rentals/offers/{o2['id']}/action/",
            {'action': 'counter', 'amount': 41500000}, format='json')
        o3 = r.data
        # lister accepts
        r = self.owner_client.post(
            f"/api/v1/rentals/offers/{o3['id']}/action/",
            {'action': 'accept'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['status'], 'accepted')
        # both parties notified of the agreement
        for party in (self.owner, self.buyer):
            self.assertTrue(Notification.objects.filter(
                user=party, title__icontains='aceite').exists())
        # the chained history is complete + ordered
        h = self.buyer_client.get(
            f"/api/v1/rentals/offers/{o1['id']}/history/").data['history']
        self.assertEqual([x['version'] for x in h], [1, 2, 3])
        self.assertEqual([x['status'] for x in h],
                         ['countered', 'countered', 'accepted'])

    def test_turn_taking_is_enforced(self):
        o1 = self._submit().data
        # the buyer authored v1 — they cannot also accept it
        r = self.buyer_client.post(
            f"/api/v1/rentals/offers/{o1['id']}/action/",
            {'action': 'accept'}, format='json')
        self.assertEqual(r.status_code, 403)
        # but the buyer CAN withdraw their own offer
        r = self.buyer_client.post(
            f"/api/v1/rentals/offers/{o1['id']}/action/",
            {'action': 'withdraw'}, format='json')
        self.assertEqual(r.data['status'], 'withdrawn')

    def test_cannot_offer_on_own_or_non_negotiable_listing(self):
        r = self.owner_client.post(
            f'/api/v1/rentals/{self.listing.id}/offers/',
            {'amount': 1000}, format='json')
        self.assertEqual(r.status_code, 400)
        fixed = _listing(self.owner, purpose='rent', price_negotiable=False,
                         title='T1 preço fixo')
        r = self.buyer_client.post(
            f'/api/v1/rentals/{fixed.id}/offers/',
            {'amount': 1000}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_invalid_amounts_rejected(self):
        for bad in (0, -5, 'abc'):
            r = self._submit(amount=bad)
            self.assertEqual(r.status_code, 400)

    def test_one_live_negotiation_per_buyer(self):
        self._submit()
        r = self._submit()
        self.assertEqual(r.status_code, 400)

    def test_resolved_offer_cannot_be_reacted(self):
        o1 = self._submit().data
        self.owner_client.post(f"/api/v1/rentals/offers/{o1['id']}/action/",
                               {'action': 'reject'}, format='json')
        r = self.owner_client.post(f"/api/v1/rentals/offers/{o1['id']}/action/",
                                   {'action': 'accept'}, format='json')
        self.assertEqual(r.status_code, 400)
