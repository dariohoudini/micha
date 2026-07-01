"""
Seed the platform product-category taxonomy.

A fresh database has zero categories, so the seller "new product" wizard's
category picker shows nothing to choose. This command seeds a sensible
Angolan-marketplace taxonomy (top-level categories + subcategories). It is
idempotent (get_or_create), so it is safe to re-run and safe as a first-boot
/ dev-setup step.

    python manage.py seed_categories
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.products.models import Category

# Top-level category -> its subcategories. Portuguese labels (the app's
# primary locale). Kept practical, not exhaustive.
TAXONOMY = {
    'Moda & Vestuário': [
        'Vestidos', 'Camisas & T-shirts', 'Calças & Jeans', 'Saias',
        'Casacos & Blusões', 'Roupa interior', 'Roupa desportiva',
        'Fatos & Blazers',
    ],
    'Calçado': [
        'Ténis', 'Sapatos', 'Sandálias', 'Botas', 'Chinelos',
    ],
    'Acessórios': [
        'Malas & Carteiras', 'Relógios', 'Óculos de sol', 'Joalharia & Bijutaria',
        'Cintos', 'Chapéus & Bonés',
    ],
    'Eletrónica': [
        'Telemóveis & Smartphones', 'Computadores & Portáteis', 'Tablets',
        'Televisões', 'Áudio & Colunas', 'Auscultadores', 'Consolas & Jogos',
        'Acessórios eletrónicos',
    ],
    'Casa & Cozinha': [
        'Móveis', 'Decoração', 'Utensílios de cozinha', 'Eletrodomésticos',
        'Roupa de cama & Banho', 'Iluminação', 'Arrumação',
    ],
    'Beleza & Cuidado pessoal': [
        'Maquilhagem', 'Cuidado da pele', 'Cuidado do cabelo', 'Perfumes',
        'Higiene pessoal',
    ],
    'Saúde & Bem-estar': [
        'Suplementos', 'Equipamento médico', 'Ortopedia',
    ],
    'Bebé & Crianças': [
        'Roupa de bebé', 'Brinquedos', 'Fraldas & Higiene', 'Puericultura',
        'Material escolar',
    ],
    'Desporto & Ar livre': [
        'Fitness & Ginásio', 'Ciclismo', 'Futebol', 'Campismo', 'Natação',
    ],
    'Alimentação & Bebidas': [
        'Mercearia', 'Bebidas', 'Snacks & Doces', 'Produtos frescos',
    ],
    'Automóvel & Motos': [
        'Peças auto', 'Acessórios auto', 'Óleos & Lubrificantes', 'Pneus',
    ],
    'Livros, Papelaria & Media': [
        'Livros', 'Papelaria', 'Material de escritório',
    ],
    'Ferramentas & Bricolage': [
        'Ferramentas manuais', 'Ferramentas elétricas', 'Jardim',
    ],
}


class Command(BaseCommand):
    help = 'Seed the platform product-category taxonomy (idempotent).'

    @transaction.atomic
    def handle(self, *args, **options):
        created_top = created_sub = 0
        for order, (top_name, subs) in enumerate(TAXONOMY.items()):
            top, was_created = Category.objects.get_or_create(
                name=top_name, owner=None,
                defaults={'parent': None, 'ordering': order, 'is_custom': False},
            )
            created_top += int(was_created)
            for s_order, sub_name in enumerate(subs):
                _, sub_created = Category.objects.get_or_create(
                    name=sub_name, owner=None,
                    defaults={'parent': top, 'ordering': s_order,
                              'is_custom': False},
                )
                created_sub += int(sub_created)

        total = Category.objects.filter(owner=None).count()
        self.stdout.write(self.style.SUCCESS(
            f'Categories seeded: +{created_top} top-level, +{created_sub} '
            f'subcategories. Platform total now {total}.'
        ))
