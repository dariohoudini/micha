"""
Property transaction flows — Viewing scheduling (doc CH11/CH14) and the
Offer/negotiation state machine (doc CH12).

These are the top of both property funnels: nobody commits to a house
unseen (viewing), and property price is negotiated (offer/counter).
Every transition is permission-checked (only the right party can act),
recorded (the negotiation history is chained + non-repudiable), and
notified to the counterpart via the shared in-app notification spine.

Deliberately NOT here (needs the payments engine wired end-to-end):
bookings/tenancies with recurring rent and the sale escrow — an
accepted offer records the AGREEMENT; money and (for sales) the
notarised title transfer proceed per the doc's legal boundary.
"""
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Listing, Offer, Viewing


def _notify(user, title, message, data=None):
    """In-app notification to the counterpart. Never raises — a
    notification failure must not break a transaction flow."""
    try:
        from apps.notifications.models import Notification
        Notification.objects.create(
            user=user, type='system', title=title[:200], message=message,
            data=data or {},
        )
    except Exception:
        pass


def _viewing_dict(v):
    return {
        'id': str(v.id),
        'listing_id': str(v.listing_id),
        'listing_title': v.listing.title,
        'requester_email': v.requester.email,
        'scheduled_at': v.scheduled_at,
        'note': v.note,
        'status': v.status,
        'created_at': v.created_at,
    }


def _offer_dict(o):
    return {
        'id': str(o.id),
        'listing_id': str(o.listing_id),
        'listing_title': o.listing.title,
        'buyer_email': o.buyer.email,
        'made_by_email': o.made_by.email,
        'amount': str(o.amount),
        'message': o.message,
        'version': o.version,
        'status': o.status,
        'created_at': o.created_at,
    }


# ── Viewings (doc CH11: requested → confirmed → done, safety-recorded) ──

class RequestViewingView(APIView):
    """POST /api/v1/rentals/<id>/viewings/ — request an in-person viewing."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            listing = Listing.objects.get(pk=pk, status='active')
        except Listing.DoesNotExist:
            return Response({'error': 'Listagem não encontrada.'}, status=404)
        if listing.lister == request.user:
            return Response({'error': 'Não pode agendar uma visita ao seu próprio anúncio.'},
                            status=400)

        scheduled_at = request.data.get('scheduled_at')
        if not scheduled_at:
            return Response({'error': 'scheduled_at é obrigatório.'}, status=400)
        from rest_framework.fields import DateTimeField
        try:
            when = DateTimeField().to_internal_value(scheduled_at)
        except Exception:
            return Response({'error': 'scheduled_at inválido.'}, status=400)
        if when <= timezone.now():
            return Response({'error': 'A visita tem de ser no futuro.'}, status=400)

        viewing = Viewing.objects.create(
            listing=listing, requester=request.user, scheduled_at=when,
            note=(request.data.get('note') or '')[:300],
        )
        _notify(listing.lister, 'Nova visita solicitada',
                f'{request.user.email} quer visitar "{listing.title}" em '
                f'{when.strftime("%d/%m/%Y %H:%M")}.',
                {'type': 'viewing', 'viewing_id': str(viewing.id),
                 'listing_id': str(listing.id)})
        return Response(_viewing_dict(viewing), status=201)


class MyViewingsView(APIView):
    """GET /api/v1/rentals/viewings/?role=requester|lister"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = request.query_params.get('role', 'requester')
        if role == 'lister':
            qs = Viewing.objects.filter(listing__lister=request.user)
        else:
            qs = Viewing.objects.filter(requester=request.user)
        qs = qs.select_related('listing', 'requester')[:50]
        return Response({'viewings': [_viewing_dict(v) for v in qs]})


class ViewingActionView(APIView):
    """POST /api/v1/rentals/viewings/<id>/action/ {action}

    confirm / complete / no_show — the LISTER only (they host the
    viewing). cancel — either party. The record survives every outcome:
    it is the safety + accountability trail.
    """
    permission_classes = [IsAuthenticated]

    TRANSITIONS = {
        'confirm':  ({'requested'}, 'confirmed'),
        'complete': ({'confirmed'}, 'completed'),
        'no_show':  ({'confirmed'}, 'no_show'),
        'cancel':   ({'requested', 'confirmed'}, 'cancelled'),
    }
    LISTER_ONLY = {'confirm', 'complete', 'no_show'}

    def post(self, request, pk):
        try:
            viewing = Viewing.objects.select_related('listing', 'requester').get(pk=pk)
        except Viewing.DoesNotExist:
            return Response({'error': 'Visita não encontrada.'}, status=404)

        is_lister = viewing.listing.lister_id == request.user.id
        is_requester = viewing.requester_id == request.user.id
        if not (is_lister or is_requester):
            return Response({'error': 'Visita não encontrada.'}, status=404)

        action = request.data.get('action')
        if action not in self.TRANSITIONS:
            return Response({'error': 'Acção inválida.'}, status=400)
        if action in self.LISTER_ONLY and not is_lister:
            return Response({'error': 'Só o anunciante pode fazer isso.'}, status=403)

        allowed_from, to_status = self.TRANSITIONS[action]
        if viewing.status not in allowed_from:
            return Response({'error': f'Transição inválida a partir de "{viewing.status}".'},
                            status=400)

        viewing.status = to_status
        viewing.responded_at = timezone.now()
        viewing.save(update_fields=['status', 'responded_at'])

        counterpart = viewing.requester if is_lister else viewing.listing.lister
        LABELS = {'confirmed': 'confirmada', 'completed': 'marcada como realizada',
                  'no_show': 'marcada como não comparecida', 'cancelled': 'cancelada'}
        _notify(counterpart, f'Visita {LABELS[to_status]}',
                f'A visita a "{viewing.listing.title}" foi {LABELS[to_status]}.',
                {'type': 'viewing', 'viewing_id': str(viewing.id)})
        return Response(_viewing_dict(viewing))


# ── Offers (doc CH12: submitted ↔ countered → accepted, recorded) ──────

class SubmitOfferView(APIView):
    """POST /api/v1/rentals/<id>/offers/ {amount, message?}"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            listing = Listing.objects.get(pk=pk, status='active')
        except Listing.DoesNotExist:
            return Response({'error': 'Listagem não encontrada.'}, status=404)
        if listing.lister == request.user:
            return Response({'error': 'Não pode fazer uma proposta ao seu próprio anúncio.'},
                            status=400)
        if not (listing.price_negotiable or listing.purpose == 'sale'):
            return Response({'error': 'Este anúncio não aceita propostas.'}, status=400)

        try:
            from decimal import Decimal
            amount = Decimal(str(request.data.get('amount')))
        except Exception:
            return Response({'error': 'Valor inválido.'}, status=400)
        if amount <= 0:
            return Response({'error': 'O valor tem de ser positivo.'}, status=400)

        # One live negotiation per buyer per listing.
        if Offer.objects.filter(listing=listing, buyer=request.user,
                                status='submitted').exists():
            return Response({'error': 'Já tem uma proposta pendente neste anúncio.'},
                            status=400)

        offer = Offer.objects.create(
            listing=listing, buyer=request.user, made_by=request.user,
            amount=amount, message=(request.data.get('message') or '')[:500],
        )
        _notify(listing.lister, 'Nova proposta recebida',
                f'{request.user.email} propôs {amount} Kz por "{listing.title}".',
                {'type': 'offer', 'offer_id': str(offer.id),
                 'listing_id': str(listing.id)})
        return Response(_offer_dict(offer), status=201)


class OfferActionView(APIView):
    """POST /api/v1/rentals/offers/<id>/action/ {action, amount?, message?}

    accept / reject / counter — only the party who did NOT author the
    current version (the ball is in their court). withdraw — only the
    author. A counter chains a NEW version (the history is complete).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            offer = Offer.objects.select_related('listing', 'buyer', 'made_by').get(pk=pk)
        except Offer.DoesNotExist:
            return Response({'error': 'Proposta não encontrada.'}, status=404)

        lister = offer.listing.lister
        is_party = request.user.id in (lister.id, offer.buyer_id)
        if not is_party:
            return Response({'error': 'Proposta não encontrada.'}, status=404)

        if offer.status != 'submitted':
            return Response({'error': f'Esta proposta já está "{offer.status}".'},
                            status=400)

        action = request.data.get('action')
        is_author = offer.made_by_id == request.user.id

        if action == 'withdraw':
            if not is_author:
                return Response({'error': 'Só quem fez a proposta pode retirá-la.'},
                                status=403)
            offer.status = 'withdrawn'
        elif action in ('accept', 'reject', 'counter'):
            if is_author:
                return Response({'error': 'A aguardar resposta da outra parte.'},
                                status=403)
            if action == 'accept':
                offer.status = 'accepted'
            elif action == 'reject':
                offer.status = 'rejected'
            else:
                try:
                    from decimal import Decimal
                    amount = Decimal(str(request.data.get('amount')))
                    assert amount > 0
                except Exception:
                    return Response({'error': 'Valor da contraproposta inválido.'},
                                    status=400)
                counter = Offer.objects.create(
                    listing=offer.listing, buyer=offer.buyer,
                    made_by=request.user, amount=amount,
                    message=(request.data.get('message') or '')[:500],
                    parent=offer, version=offer.version + 1,
                )
                offer.status = 'countered'
                offer.responded_at = timezone.now()
                offer.save(update_fields=['status', 'responded_at'])
                counterpart = offer.buyer if request.user.id == lister.id else lister
                _notify(counterpart, 'Contraproposta recebida',
                        f'Contraproposta de {amount} Kz em "{offer.listing.title}".',
                        {'type': 'offer', 'offer_id': str(counter.id)})
                return Response(_offer_dict(counter), status=201)
        else:
            return Response({'error': 'Acção inválida.'}, status=400)

        offer.responded_at = timezone.now()
        offer.save(update_fields=['status', 'responded_at'])

        if offer.status == 'accepted':
            # Acceptance = the parties agree to PROCEED at this price.
            # For a sale the notarised title transfer is OFF-PLATFORM
            # (Angola law); the lister marks the listing rented/sold when
            # concluded. The agreement itself is recorded here.
            for party in (offer.buyer, lister):
                _notify(party, 'Proposta aceite 🎉',
                        f'Acordo em "{offer.listing.title}" por {offer.amount} Kz. '
                        f'Combinem os próximos passos pelo chat.',
                        {'type': 'offer', 'offer_id': str(offer.id)})
        else:
            counterpart = offer.buyer if request.user.id == lister.id else lister
            LABELS = {'rejected': 'rejeitada', 'withdrawn': 'retirada'}
            _notify(counterpart, f'Proposta {LABELS.get(offer.status, offer.status)}',
                    f'A proposta em "{offer.listing.title}" foi {LABELS.get(offer.status, offer.status)}.',
                    {'type': 'offer', 'offer_id': str(offer.id)})
        return Response(_offer_dict(offer))


class OfferHistoryView(APIView):
    """GET /api/v1/rentals/offers/<id>/history/ — the recorded, chained
    negotiation trail (doc: non-repudiable history)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            offer = Offer.objects.select_related('listing', 'buyer').get(pk=pk)
        except Offer.DoesNotExist:
            return Response({'error': 'Proposta não encontrada.'}, status=404)
        if request.user.id not in (offer.listing.lister_id, offer.buyer_id):
            return Response({'error': 'Proposta não encontrada.'}, status=404)

        root = offer.root
        chain = []
        node = root
        while node is not None:
            chain.append(node)
            node = node.counters.order_by('created_at').first()
        return Response({'history': [_offer_dict(o) for o in chain]})


class MyOffersView(APIView):
    """GET /api/v1/rentals/offers/?role=buyer|lister"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = request.query_params.get('role', 'buyer')
        if role == 'lister':
            qs = Offer.objects.filter(listing__lister=request.user)
        else:
            qs = Offer.objects.filter(buyer=request.user)
        qs = qs.select_related('listing', 'buyer', 'made_by')[:50]
        return Response({'offers': [_offer_dict(o) for o in qs]})
