"""
apps/rentals/models.py

MICHA Express Rental Marketplace — Imóveis, Veículos & Outros Alugueres

Three rental verticals:
1. Imóveis   — Houses, apartments, offices, land
2. Veículos  — Cars, motorbikes, trucks
3. Outros    — Clothing, equipment, event items, etc.

Key design decisions:
- No payment through MICHA — listing + chat bridge only
- Owner vs Micheiro distinction on every listing
- Verification required (ID + selfie) before first listing
- Up to 15 images per listing
- Location: manual address OR GPS coordinates (user's choice)
- Properties for rent OR for sale
- Subscriptions will be added later — free for now
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


# ── Constants ────────────────────────────────────────────────────────────────

ANGOLA_PROVINCES = [
    ('Luanda', 'Luanda'), ('Benguela', 'Benguela'), ('Huambo', 'Huambo'),
    ('Huíla', 'Huíla'), ('Cabinda', 'Cabinda'), ('Uíge', 'Uíge'),
    ('Namibe', 'Namibe'), ('Malanje', 'Malanje'), ('Bié', 'Bié'),
    ('Moxico', 'Moxico'), ('Cunene', 'Cunene'), ('Cuando Cubango', 'Cuando Cubango'),
    ('Lunda Norte', 'Lunda Norte'), ('Lunda Sul', 'Lunda Sul'),
    ('Kwanza Norte', 'Kwanza Norte'), ('Kwanza Sul', 'Kwanza Sul'),
    ('Bengo', 'Bengo'), ('Zaire', 'Zaire'),
]

LISTING_CATEGORIES = [
    ('property', 'Imóvel'),
    ('vehicle',  'Veículo'),
    ('other',    'Outro aluguer'),
]

PROPERTY_TYPES = [
    ('apartment',    'Apartamento'),
    ('house',        'Vivenda / Casa'),
    ('room',         'Quarto'),
    ('office',       'Escritório'),
    ('warehouse',    'Armazém'),
    ('land',         'Terreno'),
    ('commercial',   'Espaço comercial'),
    ('villa',        'Condomínio / Villa'),
]

VEHICLE_TYPES = [
    ('car',         'Automóvel'),
    ('suv',         'SUV / 4x4'),
    ('pickup',      'Pickup'),
    ('motorcycle',  'Motociclo'),
    ('truck',       'Camião'),
    ('minibus',     'Minibus'),
    ('van',         'Carrinha'),
    ('bus',         'Autocarro'),
]

OTHER_TYPES = [
    ('clothing',    'Vestuário'),
    ('equipment',   'Equipamento'),
    ('event',       'Material para eventos'),
    ('furniture',   'Mobília'),
    ('electronics', 'Electrónica'),
    ('tools',       'Ferramentas'),
    ('other',       'Outro'),
]

LISTING_PURPOSE = [
    ('rent',  'Arrendamento'),
    ('sale',  'Venda'),
    ('both',  'Arrendamento ou Venda'),
]

LISTER_ROLE = [
    ('owner',    'Proprietário'),
    ('micheiro', 'Micheiro (Intermediário)'),
    ('agent',    'Agente Imobiliário'),
]

FURNISHING_STATUS = [
    ('furnished',   'Mobilado'),
    ('semi',        'Semi-mobilado'),
    ('unfurnished', 'Sem mobília'),
]

LISTING_STATUS = [
    ('draft',     'Rascunho'),
    ('pending',   'Pendente verificação'),
    ('active',    'Activo'),
    ('paused',    'Pausado'),
    ('rented',    'Alugado / Vendido'),
    ('rejected',  'Rejeitado'),
    ('expired',   'Expirado'),
]


class RentalVerification(models.Model):
    """
    Verification required before a user can create rental listings.
    ID document + selfie — verifies identity, not property ownership.
    Reviewed by MICHA admin.
    """
    VERIFICATION_STATUS = [
        ('pending',  'Pendente'),
        ('approved', 'Aprovado'),
        ('rejected', 'Rejeitado'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rental_verification'
    )

    # Identity documents
    id_document_type = models.CharField(
        max_length=20,
        choices=[('bi', 'BI (Bilhete de Identidade)'), ('passport', 'Passaporte'), ('residence', 'Autorização de Residência')],
        default='bi'
    )
    id_document_number = models.CharField(max_length=50)
    id_document_image = models.ImageField(
        upload_to='rentals/verification/id/',
        null=True, blank=True
    )
    selfie_image = models.ImageField(
        upload_to='rentals/verification/selfies/',
        null=True, blank=True
    )

    # For Micheiros — optional business registration
    is_micheiro = models.BooleanField(default=False)
    micheiro_description = models.TextField(
        blank=True,
        help_text="Brief description of their intermediary services"
    )
    commission_rate_pct = models.FloatField(
        null=True, blank=True,
        help_text="Typical commission percentage charged to clients"
    )

    # Review
    status = models.CharField(max_length=20, choices=VERIFICATION_STATUS, default='pending')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='rental_verifications_reviewed'
    )
    rejection_reason = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rental_verifications'

    def __str__(self):
        return f"RentalVerification({self.user.email}, {self.status})"

    @property
    def is_approved(self):
        return self.status == 'approved'


class Listing(models.Model):
    """
    Core listing model — covers properties, vehicles, and other rentals.
    Uses a category field to determine which detail fields are relevant.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lister = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rental_listings'
    )

    # ── Classification ────────────────────────────────────────────────────────
    category = models.CharField(max_length=20, choices=LISTING_CATEGORIES, db_index=True)
    purpose = models.CharField(max_length=10, choices=LISTING_PURPOSE, default='rent')
    lister_role = models.CharField(max_length=20, choices=LISTER_ROLE, default='owner')

    # ── Basic info ────────────────────────────────────────────────────────────
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=LISTING_STATUS, default='draft', db_index=True)

    # ── Pricing ───────────────────────────────────────────────────────────────
    price = models.DecimalField(max_digits=14, decimal_places=2)
    price_period = models.CharField(
        max_length=20,
        choices=[
            ('month',  'Por mês'),
            ('week',   'Por semana'),
            ('day',    'Por dia'),
            ('night',  'Por noite'),
            ('total',  'Preço total (venda)'),
            ('event',  'Por evento'),
        ],
        default='month'
    )
    price_negotiable = models.BooleanField(default=False)
    deposit_required = models.BooleanField(default=False)
    deposit_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # ── Micheiro commission disclosure (required if lister_role=micheiro) ─────
    micheiro_commission_disclosed = models.BooleanField(
        default=False,
        help_text="Micheiro has disclosed that they charge a commission"
    )
    micheiro_commission_description = models.CharField(
        max_length=200, blank=True,
        help_text="e.g. '1 mês de renda como comissão'"
    )

    # ── Contact preference ────────────────────────────────────────────────────
    contact_via_chat = models.BooleanField(default=True)
    contact_phone_visible = models.BooleanField(default=False)
    contact_whatsapp = models.CharField(max_length=20, blank=True)

    # ── Stats ─────────────────────────────────────────────────────────────────
    views_count = models.PositiveIntegerField(default=0)
    inquiries_count = models.PositiveIntegerField(default=0)
    saves_count = models.PositiveIntegerField(default=0)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'rental_listings'
        ordering = ['-published_at', '-created_at']
        indexes = [
            models.Index(fields=['category', 'status']),
            models.Index(fields=['lister', 'status']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.category}, {self.status})"

    def publish(self):
        self.status = 'active'
        self.published_at = timezone.now()
        self.save(update_fields=['status', 'published_at'])

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def formatted_price(self):
        period_labels = {
            'month': '/mês', 'week': '/semana', 'day': '/dia',
            'night': '/noite', 'total': '', 'event': '/evento',
        }
        return f"{int(self.price):,} Kz{period_labels.get(self.price_period, '')}"


class PropertyDetail(models.Model):
    """
    Property-specific details. One-to-one with Listing where category='property'.
    """
    listing = models.OneToOneField(
        Listing, on_delete=models.CASCADE, related_name='property_detail'
    )

    # Type
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES)

    # Size
    area_m2 = models.PositiveIntegerField(null=True, blank=True, help_text="Área em m²")
    floor_number = models.PositiveSmallIntegerField(null=True, blank=True)
    total_floors = models.PositiveSmallIntegerField(null=True, blank=True)

    # Rooms
    bedrooms = models.PositiveSmallIntegerField(default=0)
    bathrooms = models.PositiveSmallIntegerField(default=1)
    toilets = models.PositiveSmallIntegerField(default=0)
    living_rooms = models.PositiveSmallIntegerField(default=1)
    kitchens = models.PositiveSmallIntegerField(default=1)
    dining_rooms = models.PositiveSmallIntegerField(default=0)
    offices = models.PositiveSmallIntegerField(default=0)
    storage_rooms = models.PositiveSmallIntegerField(default=0)
    balconies = models.PositiveSmallIntegerField(default=0)
    garages = models.PositiveSmallIntegerField(default=0)

    # Furnishing
    furnishing_status = models.CharField(
        max_length=20, choices=FURNISHING_STATUS, default='unfurnished'
    )

    # Amenities — stored as JSON for flexibility
    amenities = models.JSONField(
        default=list,
        help_text="List of amenities e.g. ['water_24h', 'generator', 'security', 'pool']"
    )

    # Building features
    has_elevator = models.BooleanField(default=False)
    has_security = models.BooleanField(default=False)
    has_generator = models.BooleanField(default=False)
    has_water_24h = models.BooleanField(default=False)
    has_internet = models.BooleanField(default=False)
    has_air_conditioning = models.BooleanField(default=False)
    has_parking = models.BooleanField(default=False)
    has_garden = models.BooleanField(default=False)
    has_pool = models.BooleanField(default=False)
    has_gym = models.BooleanField(default=False)
    pets_allowed = models.BooleanField(default=False)
    available_from = models.DateField(null=True, blank=True)

    # Property condition
    property_condition = models.CharField(
        max_length=20,
        choices=[
            ('new',        'Novo'),
            ('excellent',  'Excelente estado'),
            ('good',       'Bom estado'),
            ('needs_work', 'Precisa de obras'),
        ],
        default='good'
    )
    year_built = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'rental_property_details'


# Standard amenities for checkboxes in frontend
PROPERTY_AMENITIES = [
    ('water_24h',        'Água 24h'),
    ('generator',        'Gerador'),
    ('security',         'Segurança/Porteiro'),
    ('pool',             'Piscina'),
    ('gym',              'Ginásio'),
    ('parking',          'Estacionamento'),
    ('garden',           'Jardim'),
    ('elevator',         'Elevador'),
    ('internet',         'Internet incluída'),
    ('air_conditioning', 'Ar condicionado'),
    ('solar_panels',     'Painéis solares'),
    ('satellite_tv',     'TV por satélite'),
    ('intercom',         'Intercomunicador'),
    ('cctv',             'Câmeras de segurança'),
    ('pets_allowed',     'Animais permitidos'),
    ('furnished_kitchen','Cozinha equipada'),
    ('laundry',          'Lavandaria'),
    ('storage',          'Arrecadação'),
]


class VehicleDetail(models.Model):
    """Vehicle-specific details for car/motorbike/truck rentals."""
    listing = models.OneToOneField(
        Listing, on_delete=models.CASCADE, related_name='vehicle_detail'
    )

    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPES)
    make = models.CharField(max_length=50, help_text="e.g. Toyota")
    model = models.CharField(max_length=50, help_text="e.g. Land Cruiser")
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    color = models.CharField(max_length=30, blank=True)
    mileage_km = models.PositiveIntegerField(null=True, blank=True)
    fuel_type = models.CharField(
        max_length=20,
        choices=[('petrol','Gasolina'), ('diesel','Gasóleo'), ('electric','Eléctrico'), ('hybrid','Híbrido')],
        default='petrol'
    )
    transmission = models.CharField(
        max_length=20,
        choices=[('manual','Manual'), ('automatic','Automático'), ('semi','Semi-automático')],
        default='manual'
    )
    seats = models.PositiveSmallIntegerField(default=5)
    doors = models.PositiveSmallIntegerField(default=4)

    # Features
    has_ac = models.BooleanField(default=False)
    has_gps = models.BooleanField(default=False)
    has_bluetooth = models.BooleanField(default=False)
    has_sunroof = models.BooleanField(default=False)
    has_4wd = models.BooleanField(default=False)

    # Rental conditions
    driver_included = models.BooleanField(default=False)
    min_rental_days = models.PositiveSmallIntegerField(default=1)
    requires_driving_license = models.BooleanField(default=True)
    min_driver_age = models.PositiveSmallIntegerField(default=21)
    fuel_policy = models.CharField(
        max_length=20,
        choices=[('full_to_full','Cheio para cheio'), ('included','Combustível incluído'), ('pay_as_you_go','Paga conforme usa')],
        default='full_to_full'
    )
    insurance_included = models.BooleanField(default=False)
    plate_number = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = 'rental_vehicle_details'


class OtherRentalDetail(models.Model):
    """Details for clothing, equipment, event items, etc."""
    listing = models.OneToOneField(
        Listing, on_delete=models.CASCADE, related_name='other_detail'
    )

    item_type = models.CharField(max_length=20, choices=OTHER_TYPES)
    brand = models.CharField(max_length=100, blank=True)
    size = models.CharField(max_length=50, blank=True, help_text="e.g. M, L, 42, 2m×3m")
    color = models.CharField(max_length=50, blank=True)
    condition = models.CharField(
        max_length=20,
        choices=[('new','Novo'), ('like_new','Como novo'), ('good','Bom estado'), ('fair','Estado razoável')],
        default='good'
    )
    quantity_available = models.PositiveSmallIntegerField(default=1)
    min_rental_days = models.PositiveSmallIntegerField(default=1)
    max_rental_days = models.PositiveSmallIntegerField(null=True, blank=True)
    delivery_available = models.BooleanField(default=False)
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'rental_other_details'


class ListingLocation(models.Model):
    """
    Location for a listing — either manual address entry OR GPS coordinates.
    User's choice. GPS gives map pin, address gives text display.
    """
    listing = models.OneToOneField(
        Listing, on_delete=models.CASCADE, related_name='location'
    )

    # Manual address
    province = models.CharField(max_length=50, choices=ANGOLA_PROVINCES, default='Luanda')
    municipality = models.CharField(max_length=100, blank=True, help_text="e.g. Talatona, Belas, Maianga")
    neighbourhood = models.CharField(max_length=100, blank=True, help_text="e.g. Futungo de Belas")
    street = models.CharField(max_length=200, blank=True)
    address_complement = models.CharField(max_length=200, blank=True, help_text="e.g. Bloco 5, Apt 12B")

    # GPS coordinates (optional — user drops pin on map)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    has_gps = models.BooleanField(default=False)

    # Display options — lister can choose privacy level
    location_privacy = models.CharField(
        max_length=20,
        choices=[
            ('exact',        'Localização exacta'),
            ('neighbourhood','Só o bairro'),
            ('municipality', 'Só o município'),
        ],
        default='neighbourhood',
        help_text="How precisely to show location to potential renters"
    )

    class Meta:
        db_table = 'rental_listing_locations'

    def get_display_location(self):
        """Returns location string based on privacy setting."""
        parts = []
        if self.location_privacy in ('exact', 'neighbourhood') and self.neighbourhood:
            parts.append(self.neighbourhood)
        if self.municipality:
            parts.append(self.municipality)
        if self.province:
            parts.append(self.province)
        return ', '.join(parts) if parts else self.province


class ListingImage(models.Model):
    """Up to 15 images per listing. First image = cover photo."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, related_name='images'
    )
    image = models.ImageField(upload_to='rentals/images/%Y/%m/')
    order = models.PositiveSmallIntegerField(default=0)
    caption = models.CharField(max_length=200, blank=True)
    is_cover = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rental_listing_images'
        ordering = ['order', 'created_at']

    def save(self, *args, **kwargs):
        # Enforce 15 image limit
        if not self.pk:
            existing = ListingImage.objects.filter(listing=self.listing).count()
            if existing >= 15:
                raise ValueError("Maximum 15 images per listing.")
        super().save(*args, **kwargs)


class ListingInquiry(models.Model):
    """
    Inquiry from a potential renter/buyer to a lister.
    Creates a chat conversation — bridges to existing chat system.
    """
    STATUS = [
        ('pending',   'Pendente'),
        ('accepted',  'Aceite'),
        ('declined',  'Recusado'),
        ('completed', 'Concluído'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, related_name='inquiries'
    )
    inquirer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rental_inquiries'
    )

    # Initial message
    message = models.TextField(blank=True)
    move_in_date = models.DateField(null=True, blank=True)
    rental_duration = models.CharField(max_length=100, blank=True, help_text="e.g. 6 meses, 1 ano")

    # Chat conversation ID (from existing chat system)
    chat_conversation_id = models.UUIDField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rental_inquiries'
        unique_together = [('listing', 'inquirer')]

    def __str__(self):
        return f"Inquiry({self.inquirer.email} → {self.listing.title})"


class SavedListing(models.Model):
    """User saves/favourites a listing."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_listings'
    )
    listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, related_name='saved_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rental_saved_listings'
        unique_together = [('user', 'listing')]
