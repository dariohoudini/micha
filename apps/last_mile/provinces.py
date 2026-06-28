"""
Angola's 18 provinces + zone classification (doc CH2).

zone_class drives the base rate and transit time. Explicit Luanda-origin
rows are seeded; any other pair falls back to `classify_zone` using a
province-adjacency map (so the matrix supports arbitrary origin/dest as
sellers expand beyond Luanda).
"""

PROVINCES = [
    'Bengo', 'Benguela', 'Bié', 'Cabinda', 'Cuando Cubango',
    'Cuanza Norte', 'Cuanza Sul', 'Cunene', 'Huambo', 'Huíla', 'Luanda',
    'Lunda Norte', 'Lunda Sul', 'Malanje', 'Moxico', 'Namibe', 'Uíge',
    'Zaire',
]

SAME_CITY = 'same_city'
SAME_PROVINCE = 'same_province'
ADJACENT = 'adjacent'
DOMESTIC = 'domestic'
REMOTE = 'remote'

ZONE_CLASS_CHOICES = [
    (SAME_CITY, 'Same city'), (SAME_PROVINCE, 'Same province'),
    (ADJACENT, 'Adjacent'), (DOMESTIC, 'Domestic'), (REMOTE, 'Remote'),
]

# Zone-class rate table (cents) — admin-tunable seed (doc CH2.2).
ZONE_RATES = {
    SAME_CITY: {'base': 150_000, 'per_kg': 20_000, 'days': (1, 2)},
    SAME_PROVINCE: {'base': 200_000, 'per_kg': 25_000, 'days': (1, 3)},
    ADJACENT: {'base': 300_000, 'per_kg': 35_000, 'days': (2, 4)},
    DOMESTIC: {'base': 500_000, 'per_kg': 50_000, 'days': (3, 6)},
    REMOTE: {'base': 800_000, 'per_kg': 80_000, 'days': (7, 14)},
}

# Province adjacency (shares a border) — used for fallback classification.
ADJACENCY = {
    'Luanda': {'Bengo', 'Cuanza Norte', 'Cuanza Sul'},
    'Bengo': {'Luanda', 'Cuanza Norte', 'Uíge', 'Zaire'},
    'Cuanza Norte': {'Luanda', 'Bengo', 'Cuanza Sul', 'Malanje', 'Uíge'},
    'Cuanza Sul': {'Luanda', 'Cuanza Norte', 'Benguela', 'Huambo', 'Bié',
                   'Malanje'},
    'Benguela': {'Cuanza Sul', 'Huambo', 'Huíla', 'Namibe'},
    'Huambo': {'Cuanza Sul', 'Benguela', 'Bié', 'Huíla'},
    'Bié': {'Cuanza Sul', 'Huambo', 'Malanje', 'Moxico', 'Huíla',
            'Cuando Cubango'},
    'Huíla': {'Benguela', 'Huambo', 'Bié', 'Namibe', 'Cunene',
              'Cuando Cubango'},
    'Namibe': {'Benguela', 'Huíla', 'Cunene'},
    'Cunene': {'Huíla', 'Namibe', 'Cuando Cubango'},
    'Cuando Cubango': {'Bié', 'Huíla', 'Cunene', 'Moxico'},
    'Moxico': {'Bié', 'Cuando Cubango', 'Malanje', 'Lunda Sul'},
    'Malanje': {'Cuanza Norte', 'Cuanza Sul', 'Bié', 'Moxico', 'Lunda Norte',
                'Lunda Sul', 'Uíge'},
    'Lunda Norte': {'Malanje', 'Lunda Sul', 'Uíge'},
    'Lunda Sul': {'Malanje', 'Moxico', 'Lunda Norte'},
    'Uíge': {'Bengo', 'Cuanza Norte', 'Malanje', 'Lunda Norte', 'Zaire'},
    'Zaire': {'Bengo', 'Uíge', 'Cabinda'},
    'Cabinda': {'Zaire'},   # exclave — air only in practice
}

# Provinces that are operationally remote (poor roads / long transit).
REMOTE_PROVINCES = {'Cuando Cubango', 'Moxico', 'Lunda Norte', 'Lunda Sul',
                    'Cabinda'}

# COD availability per destination province (doc CH2.1).
COD_PROVINCES = {'Luanda', 'Bengo', 'Cuanza Norte', 'Benguela', 'Huíla',
                 'Huambo', 'Cuanza Sul'}

REMOTE_MULTIPLIER = 1.5
COD_SURCHARGE_CENTS = 50_000          # 500 Kz
VOLUMETRIC_DIVISOR = 5000             # road (6000 for air)
MOTORBIKE_MAX_GRAMS = 10_000          # 10 kg


def classify_zone(origin, destination):
    """Fallback zone classification for any province pair (doc CH2)."""
    if origin == destination:
        return SAME_PROVINCE
    if destination in REMOTE_PROVINCES or origin in REMOTE_PROVINCES:
        return REMOTE
    if destination in ADJACENCY.get(origin, set()):
        return ADJACENT
    return DOMESTIC


def cod_available(destination):
    return destination in COD_PROVINCES
