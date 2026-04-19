"""
apps/rentals/views.py
"""
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q
from django.utils import timezone

from .models import (
    Listing, ListingImage, ListingInquiry, RentalVerification,
    SavedListing, PROPERTY_AMENITIES
)
from .serializers import (
    ListingListSerializer, ListingDetailSerializer, CreateListingSerializer,
    ListingImageSerializer, ListingInquirySerializer, RentalVerificationSerializer
)


# ── Browse / Search ───────────────────────────────────────────────────────────

class ListingBrowseView(generics.ListAPIView):
    """
    GET /api/rentals/browse/

    Public browse — anyone can see listings.
    Query params:
        category    — property | vehicle | other
        purpose     — rent | sale
        province    — e.g. Luanda
        municipality
        min_price
        max_price
        bedrooms    — (property only)
        property_type
        vehicle_type
        lister_role — owner | micheiro | agent
        search      — full text search on title + description
        ordering    — -created_at | price | -price
    """
    permission_classes = [AllowAny]
    serializer_class = ListingListSerializer

    def get_queryset(self):
        qs = Listing.objects.filter(status='active').select_related(
            'location', 'lister'
        ).prefetch_related('images')

        p = self.request.query_params

        # Category & purpose
        if p.get('category'):
            qs = qs.filter(category=p['category'])
        if p.get('purpose'):
            qs = qs.filter(purpose=p['purpose'])
        if p.get('lister_role'):
            qs = qs.filter(lister_role=p['lister_role'])

        # Location
        if p.get('province'):
            qs = qs.filter(location__province=p['province'])
        if p.get('municipality'):
            qs = qs.filter(location__municipality__icontains=p['municipality'])

        # Price range
        if p.get('min_price'):
            qs = qs.filter(price__gte=p['min_price'])
        if p.get('max_price'):
            qs = qs.filter(price__lte=p['max_price'])

        # Property filters
        if p.get('property_type'):
            qs = qs.filter(property_detail__property_type=p['property_type'])
        if p.get('bedrooms'):
            qs = qs.filter(property_detail__bedrooms__gte=p['bedrooms'])
        if p.get('bathrooms'):
            qs = qs.filter(property_detail__bathrooms__gte=p['bathrooms'])
        if p.get('min_area'):
            qs = qs.filter(property_detail__area_m2__gte=p['min_area'])
        if p.get('furnishing'):
            qs = qs.filter(property_detail__furnishing_status=p['furnishing'])

        # Amenities filter
        amenities = p.getlist('amenity')
        for amenity in amenities:
            qs = qs.filter(property_detail__amenities__contains=[amenity])

        # Vehicle filters
        if p.get('vehicle_type'):
            qs = qs.filter(vehicle_detail__vehicle_type=p['vehicle_type'])
        if p.get('make'):
            qs = qs.filter(vehicle_detail__make__icontains=p['make'])

        # Full text search
        if p.get('search'):
            qs = qs.filter(
                Q(title__icontains=p['search']) |
                Q(description__icontains=p['search']) |
                Q(location__municipality__icontains=p['search']) |
                Q(location__neighbourhood__icontains=p['search'])
            )

        # Ordering
        ordering = p.get('ordering', '-published_at')
        if ordering in ('-created_at', 'price', '-price', '-published_at', '-views_count'):
            qs = qs.order_by(ordering)

        return qs.distinct()


class ListingDetailView(generics.RetrieveAPIView):
    """GET /api/rentals/<id>/ — Public listing detail."""
    permission_classes = [AllowAny]
    serializer_class = ListingDetailSerializer
    queryset = Listing.objects.filter(status='active').select_related(
        'location', 'property_detail', 'vehicle_detail', 'other_detail', 'lister'
    ).prefetch_related('images')

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment view count
        Listing.objects.filter(pk=instance.pk).update(
            views_count=instance.views_count + 1
        )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


# ── Lister (Seller) Management ────────────────────────────────────────────────

class MyListingsView(generics.ListAPIView):
    """GET /api/rentals/my/ — Lister's own listings."""
    permission_classes = [IsAuthenticated]
    serializer_class = ListingListSerializer

    def get_queryset(self):
        return Listing.objects.filter(
            lister=self.request.user
        ).prefetch_related('images').select_related('location').order_by('-created_at')


class CreateListingView(generics.CreateAPIView):
    """
    POST /api/rentals/create/
    Creates a new listing. Requires rental verification to be approved.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CreateListingSerializer

    def perform_create(self, serializer):
        # Check verification
        try:
            verification = self.request.user.rental_verification
            if not verification.is_approved:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(
                    "A sua verificação de identidade está pendente. "
                    "Submeta o seu BI e selfie para começar a publicar."
                )
        except RentalVerification.DoesNotExist:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Verificação de identidade necessária. "
                "Faça a verificação antes de publicar anúncios."
            )

        listing = serializer.save(lister=self.request.user, status='pending')
        return listing


class UpdateListingView(generics.UpdateAPIView):
    """PUT/PATCH /api/rentals/<id>/update/"""
    permission_classes = [IsAuthenticated]
    serializer_class = CreateListingSerializer

    def get_queryset(self):
        return Listing.objects.filter(lister=self.request.user)


class DeleteListingView(generics.DestroyAPIView):
    """DELETE /api/rentals/<id>/delete/"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Listing.objects.filter(lister=self.request.user)


class PublishListingView(APIView):
    """POST /api/rentals/<id>/publish/ — Publish a draft listing."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            listing = Listing.objects.get(pk=pk, lister=request.user)
            if listing.images.count() == 0:
                return Response(
                    {'error': 'Adicione pelo menos uma foto antes de publicar.'},
                    status=400
                )
            listing.status = 'pending'
            listing.save()
            return Response({'status': 'pending', 'message': 'Anúncio enviado para revisão.'})
        except Listing.DoesNotExist:
            return Response({'error': 'Listagem não encontrada.'}, status=404)


class PauseListingView(APIView):
    """POST /api/rentals/<id>/pause/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            listing = Listing.objects.get(pk=pk, lister=request.user, status='active')
            listing.status = 'paused'
            listing.save()
            return Response({'status': 'paused'})
        except Listing.DoesNotExist:
            return Response({'error': 'Listagem não encontrada ou não activa.'}, status=404)


class MarkRentedView(APIView):
    """POST /api/rentals/<id>/mark-rented/ — Mark as rented/sold."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            listing = Listing.objects.get(pk=pk, lister=request.user)
            listing.status = 'rented'
            listing.save()
            return Response({'status': 'rented'})
        except Listing.DoesNotExist:
            return Response({'error': 'Listagem não encontrada.'}, status=404)


# ── Images ────────────────────────────────────────────────────────────────────

class UploadListingImageView(APIView):
    """POST /api/rentals/<id>/images/ — Upload image for a listing."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            listing = Listing.objects.get(pk=pk, lister=request.user)
        except Listing.DoesNotExist:
            return Response({'error': 'Listagem não encontrada.'}, status=404)

        if listing.images.count() >= 15:
            return Response({'error': 'Máximo de 15 fotos por listagem.'}, status=400)

        image_file = request.FILES.get('image')
        if not image_file:
            return Response({'error': 'Nenhuma imagem fornecida.'}, status=400)

        is_cover = listing.images.count() == 0  # First image = cover
        order = listing.images.count()

        img = ListingImage.objects.create(
            listing=listing,
            image=image_file,
            order=order,
            is_cover=is_cover,
            caption=request.data.get('caption', ''),
        )
        return Response(ListingImageSerializer(img, context={'request': request}).data, status=201)

    def delete(self, request, pk):
        """DELETE /api/rentals/<id>/images/<image_id>/"""
        image_id = request.data.get('image_id')
        try:
            img = ListingImage.objects.get(
                id=image_id, listing__id=pk, listing__lister=request.user
            )
            was_cover = img.is_cover
            img.delete()

            # If deleted was cover, make next image the cover
            if was_cover:
                next_img = ListingImage.objects.filter(listing__id=pk).first()
                if next_img:
                    next_img.is_cover = True
                    next_img.save()

            return Response({'deleted': True})
        except ListingImage.DoesNotExist:
            return Response({'error': 'Imagem não encontrada.'}, status=404)


# ── Inquiries / Chat Bridge ───────────────────────────────────────────────────

class CreateInquiryView(APIView):
    """
    POST /api/rentals/<id>/inquire/

    Creates an inquiry and starts a chat conversation.
    This is the bridge between the rental listing and the chat system.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            listing = Listing.objects.get(pk=pk, status='active')
        except Listing.DoesNotExist:
            return Response({'error': 'Listagem não encontrada.'}, status=404)

        if listing.lister == request.user:
            return Response({'error': 'Não pode fazer uma proposta ao seu próprio anúncio.'}, status=400)

        # Check if already inquired
        existing = ListingInquiry.objects.filter(
            listing=listing, inquirer=request.user
        ).first()
        if existing:
            return Response({
                'inquiry_id': str(existing.id),
                'chat_conversation_id': str(existing.chat_conversation_id) if existing.chat_conversation_id else None,
                'already_exists': True,
            })

        inquiry = ListingInquiry.objects.create(
            listing=listing,
            inquirer=request.user,
            message=request.data.get('message', ''),
            move_in_date=request.data.get('move_in_date'),
            rental_duration=request.data.get('rental_duration', ''),
        )

        # Create chat conversation (bridge to chat system)
        chat_conversation_id = self._create_chat_conversation(
            listing=listing,
            inquirer=request.user,
            initial_message=request.data.get('message', f"Olá! Tenho interesse no seu anúncio: {listing.title}"),
        )

        if chat_conversation_id:
            inquiry.chat_conversation_id = chat_conversation_id
            inquiry.save()

        # Increment inquiry count
        Listing.objects.filter(pk=pk).update(
            inquiries_count=listing.inquiries_count + 1
        )

        return Response({
            'inquiry_id': str(inquiry.id),
            'chat_conversation_id': str(chat_conversation_id) if chat_conversation_id else None,
            'redirect_to_chat': True,
        }, status=201)

    def _create_chat_conversation(self, listing, inquirer, initial_message):
        """Creates a chat conversation between inquirer and lister."""
        try:
            from apps.chat.models import Conversation, Message
            conv = Conversation.objects.create(
                buyer=inquirer,
                seller=listing.lister,
                listing_id=listing.id,
                listing_title=listing.title,
            )
            Message.objects.create(
                conversation=conv,
                sender=inquirer,
                content=initial_message,
            )
            return conv.id
        except Exception:
            # Chat app may have different model structure
            return None


# ── Save / Unsave ─────────────────────────────────────────────────────────────

class SaveListingView(APIView):
    """POST/DELETE /api/rentals/<id>/save/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            listing = Listing.objects.get(pk=pk)
            saved, created = SavedListing.objects.get_or_create(
                user=request.user, listing=listing
            )
            if created:
                Listing.objects.filter(pk=pk).update(
                    saves_count=listing.saves_count + 1
                )
            return Response({'saved': True})
        except Listing.DoesNotExist:
            return Response({'error': 'Listagem não encontrada.'}, status=404)

    def delete(self, request, pk):
        SavedListing.objects.filter(user=request.user, listing_id=pk).delete()
        return Response({'saved': False})


class SavedListingsView(generics.ListAPIView):
    """GET /api/rentals/saved/ — User's saved listings."""
    permission_classes = [IsAuthenticated]
    serializer_class = ListingListSerializer

    def get_queryset(self):
        saved_ids = SavedListing.objects.filter(
            user=self.request.user
        ).values_list('listing_id', flat=True)
        return Listing.objects.filter(id__in=saved_ids).prefetch_related('images').select_related('location')


# ── Verification ──────────────────────────────────────────────────────────────

class SubmitVerificationView(APIView):
    """POST /api/rentals/verify/ — Submit ID + selfie for verification."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        try:
            v = request.user.rental_verification
            return Response(RentalVerificationSerializer(v).data)
        except RentalVerification.DoesNotExist:
            return Response({'status': 'not_submitted'})

    def post(self, request):
        # Check if already submitted
        existing = RentalVerification.objects.filter(user=request.user).first()
        if existing and existing.status == 'approved':
            return Response({'error': 'Já verificado.', 'status': 'approved'})

        data = {
            'id_document_type': request.data.get('id_document_type', 'bi'),
            'id_document_number': request.data.get('id_document_number', ''),
            'is_micheiro': request.data.get('is_micheiro', False),
            'micheiro_description': request.data.get('micheiro_description', ''),
            'commission_rate_pct': request.data.get('commission_rate_pct'),
        }

        if not data['id_document_number']:
            return Response({'error': 'Número do documento obrigatório.'}, status=400)

        if not request.FILES.get('id_document_image'):
            return Response({'error': 'Foto do documento obrigatória.'}, status=400)

        if not request.FILES.get('selfie_image'):
            return Response({'error': 'Selfie obrigatória.'}, status=400)

        v, created = RentalVerification.objects.update_or_create(
            user=request.user,
            defaults={
                **data,
                'id_document_image': request.FILES['id_document_image'],
                'selfie_image': request.FILES['selfie_image'],
                'status': 'pending',
            }
        )

        # Notify admins
        try:
            from apps.ai_engine.tasks import send_push_notification
            from django.contrib.auth import get_user_model
            User = get_user_model()
            for admin in User.objects.filter(is_staff=True):
                send_push_notification.delay(
                    user_id=str(admin.id),
                    title="Nova verificação de anunciante",
                    body=f"{request.user.email} submeteu verificação de identidade.",
                    data={'type': 'rental_verification', 'user_id': str(request.user.id)}
                )
        except Exception:
            pass

        return Response({
            'status': 'pending',
            'message': 'Verificação submetida. Será analisada em até 24h.',
        }, status=201)


# ── Admin ─────────────────────────────────────────────────────────────────────

class AdminVerificationsView(APIView):
    """GET /api/rentals/admin/verifications/ — Pending verifications."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        status_filter = request.query_params.get('status', 'pending')
        verifications = RentalVerification.objects.filter(
            status=status_filter
        ).select_related('user').order_by('-submitted_at')

        data = []
        for v in verifications:
            data.append({
                'id': str(v.id),
                'user_email': v.user.email,
                'id_document_type': v.id_document_type,
                'id_document_number': v.id_document_number,
                'is_micheiro': v.is_micheiro,
                'status': v.status,
                'submitted_at': v.submitted_at.isoformat(),
            })
        return Response(data)

    def post(self, request):
        """Approve or reject a verification."""
        verification_id = request.data.get('verification_id')
        action = request.data.get('action')  # 'approve' or 'reject'

        try:
            v = RentalVerification.objects.get(id=verification_id)
        except RentalVerification.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

        if action == 'approve':
            v.status = 'approved'
            v.reviewed_by = request.user
            v.reviewed_at = timezone.now()
            v.save()

            # Notify user
            try:
                from apps.ai_engine.tasks import send_push_notification
                send_push_notification.delay(
                    user_id=str(v.user.id),
                    title="Verificação aprovada! ✓",
                    body="A sua identidade foi verificada. Já pode publicar anúncios na MICHA.",
                    data={'type': 'verification_approved'}
                )
            except Exception:
                pass

            return Response({'status': 'approved'})

        elif action == 'reject':
            v.status = 'rejected'
            v.rejection_reason = request.data.get('reason', '')
            v.reviewed_by = request.user
            v.reviewed_at = timezone.now()
            v.save()

            try:
                from apps.ai_engine.tasks import send_push_notification
                send_push_notification.delay(
                    user_id=str(v.user.id),
                    title="Verificação não aprovada",
                    body=f"A sua verificação foi rejeitada: {v.rejection_reason}",
                    data={'type': 'verification_rejected'}
                )
            except Exception:
                pass

            return Response({'status': 'rejected'})

        return Response({'error': 'Invalid action'}, status=400)


class AdminListingsView(APIView):
    """GET/POST /api/rentals/admin/listings/ — Review pending listings."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        status_filter = request.query_params.get('status', 'pending')
        listings = Listing.objects.filter(
            status=status_filter
        ).select_related('lister', 'location').order_by('-created_at')[:50]

        return Response(ListingListSerializer(
            listings, many=True, context={'request': request}
        ).data)

    def post(self, request):
        listing_id = request.data.get('listing_id')
        action = request.data.get('action')

        try:
            listing = Listing.objects.get(id=listing_id)
        except Listing.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

        if action == 'approve':
            listing.publish()
            return Response({'status': 'active'})
        elif action == 'reject':
            listing.status = 'rejected'
            listing.save()
            return Response({'status': 'rejected'})

        return Response({'error': 'Invalid action'}, status=400)


# ── Meta ──────────────────────────────────────────────────────────────────────

class RentalsMetaView(APIView):
    """GET /api/rentals/meta/ — Constants for frontend forms."""
    permission_classes = [AllowAny]

    def get(self, request):
        from .models import (
            LISTING_CATEGORIES, PROPERTY_TYPES, VEHICLE_TYPES, OTHER_TYPES,
            LISTING_PURPOSE, LISTER_ROLE, FURNISHING_STATUS,
            ANGOLA_PROVINCES, PROPERTY_AMENITIES
        )
        return Response({
            'categories': LISTING_CATEGORIES,
            'property_types': PROPERTY_TYPES,
            'vehicle_types': VEHICLE_TYPES,
            'other_types': OTHER_TYPES,
            'purposes': LISTING_PURPOSE,
            'lister_roles': LISTER_ROLE,
            'furnishing_statuses': FURNISHING_STATUS,
            'provinces': ANGOLA_PROVINCES,
            'amenities': PROPERTY_AMENITIES,
        })
