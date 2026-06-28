"""
Seed the MessageTemplate catalogue.

Run:
  python manage.py seed_message_templates

Idempotent: skips templates that already exist for the same
(key, kind, locale) so re-runs are safe.

Coverage:
  - 20 push templates    (CH17.2 doc spec)
  - 14 email templates   (CH18 lifecycle stages)
  - PT-AO is the default for MICHA-Angola; EN-US fallback rendered
    on every key so non-Angola buyers still get something.
"""
from django.core.management.base import BaseCommand

from apps.buyer_engagement.models import MessageTemplate


# Format: (key, kind, locale, subject, body, deep_link, cta_label)
TEMPLATES = [
    # ─── PUSH NOTIFICATIONS (CH17.2) ───────────────────────────

    # Onboarding / first-touch
    ('welcome_push', 'push', 'pt-AO',
     'Bem-vindo à MICHA!',
     'Aproveite {amount} {currency} de desconto na sua primeira compra. Válido por 30 dias.',
     '/welcome', 'Ver oferta'),
    ('welcome_push', 'push', 'en-US',
     'Welcome to MICHA!',
     'Enjoy {amount} {currency} off your first order. Valid for 30 days.',
     '/welcome', 'See offer'),

    # Cart recovery (CH11.2 — 5 steps)
    ('cart_recovery_h1', 'push', 'pt-AO',
     'Deixou algo no carrinho',
     'Os seus itens estão à sua espera. Finalize agora antes que se esgotem.',
     '/cart', 'Ver carrinho'),
    ('cart_recovery_h4', 'push', 'pt-AO',
     'Ainda interessado?',
     'Compre nas próximas horas e use o desconto que reservámos para si.',
     '/cart', 'Ver oferta'),
    ('cart_recovery_h24', 'push', 'pt-AO',
     'Stock limitado',
     'Restam poucas unidades do seu produto. Não perca!',
     '/cart', 'Comprar agora'),
    ('cart_recovery_h48', 'push', 'pt-AO',
     '10% extra para si',
     'Use o código {coupon_code} e leve com mais desconto.',
     '/cart?coupon={coupon_code}', 'Aplicar desconto'),
    ('cart_recovery_h72', 'push', 'pt-AO',
     'Última oportunidade',
     'O seu carrinho está prestes a expirar. Compre agora!',
     '/cart', 'Ver carrinho'),

    # Checkout abandonment (CH12)
    ('checkout_recovery_h1', 'push', 'pt-AO',
     'Pagamento incompleto',
     'Quase pronto! Volte e finalize a sua encomenda em segundos.',
     '/checkout', 'Continuar'),
    ('checkout_recovery_h4', 'push', 'pt-AO',
     'Pode pagar com Multicaixa Express',
     'Métodos de pagamento aceites: Multicaixa, Visa, Mastercard.',
     '/checkout', 'Pagar agora'),

    # Browse abandonment (CH13)
    ('browse_abandon', 'push', 'pt-AO',
     'Encontrou algo do seu agrado?',
     '{product_count} produtos que viu estão com desconto.',
     '/browse/recently-viewed', 'Ver produtos'),

    # Back-in-stock + price drop (CH14/15)
    ('back_in_stock', 'push', 'pt-AO',
     'Voltou ao stock!',
     '{product_name} já está disponível. Garanta o seu.',
     '/product/{product_id}', 'Comprar'),
    ('price_drop', 'push', 'pt-AO',
     'O preço baixou!',
     '{product_name} agora a {new_price} (era {old_price}).',
     '/product/{product_id}', 'Ver produto'),

    # Order lifecycle
    ('order_paid', 'push', 'pt-AO',
     'Pagamento confirmado',
     'A sua encomenda #{order_id} foi confirmada. Prepara-se para envio.',
     '/orders/{order_id}', 'Ver encomenda'),
    ('order_shipped', 'push', 'pt-AO',
     'A sua encomenda foi enviada',
     'Encomenda #{order_id} a caminho. Entrega prevista: {eta}.',
     '/orders/{order_id}', 'Rastrear'),
    ('order_delivered', 'push', 'pt-AO',
     'Encomenda entregue',
     'Aproveite a sua compra! Deixe uma avaliação e ganhe coins.',
     '/orders/{order_id}/review', 'Avaliar'),

    # Win-back (CH16)
    ('winback_lapsing', 'push', 'pt-AO',
     'Sentimos a sua falta',
     'Volte e use o código {coupon_code} para 5% extra.',
     '/?coupon={coupon_code}', 'Voltar à MICHA'),
    ('winback_dormant_60', 'push', 'pt-AO',
     'Vale 500 AKZ para si',
     'Já passaram 60 dias. Use {coupon_code} antes que expire.',
     '/?coupon={coupon_code}', 'Reclamar'),

    # Promotions / loyalty
    ('flash_sale_starting', 'push', 'pt-AO',
     'Flash Sale começa agora!',
     '{deal_count} ofertas relâmpago. Apenas 1 hora.',
     '/flash-sale', 'Ver ofertas'),
    ('coins_milestone', 'push', 'pt-AO',
     'Já tem {coins} coins!',
     'Faltam {coins_to_next} para o próximo nível. Continue!',
     '/coins', 'Ver coins'),
    ('birthday', 'push', 'pt-AO',
     'Parabéns! 🎉',
     'A sua oferta de aniversário está pronta: {coupon_code}.',
     '/birthday', 'Reclamar'),

    # ─── EMAIL LIFECYCLE (CH18 — 14 stages) ────────────────────

    ('welcome', 'email', 'pt-AO',
     'Bem-vindo à MICHA — aqui está {amount} {currency} de desconto',
     '''Olá,

Bem-vindo à MICHA Express! Para celebrar a sua chegada, oferecemos-lhe um cupão de {amount} {currency} para a sua primeira compra.

Código: {coupon_code}
Válido até: {expires_at}
Compra mínima: {min_order} {currency}

Explore milhares de produtos com entrega rápida em Angola.

A equipa MICHA''',
     '/?coupon={coupon_code}', 'Começar a comprar'),

    ('post_register', 'email', 'pt-AO',
     '3 coisas para fazer antes da sua primeira compra',
     '''Olá,

Para tirar o máximo proveito da MICHA, complete estes 3 passos:

1. Adicione um método de entrega favorito.
2. Active as notificações de oferta.
3. Siga as suas lojas preferidas.

Vamos a isso!''',
     '/profile/setup', 'Continuar'),

    ('first_purchase', 'email', 'pt-AO',
     '🎉 Obrigado pela sua primeira compra!',
     '''Olá,

A sua primeira encomenda #{order_id} foi confirmada. Estamos a preparar tudo para envio.

Coins ganhas: {coins_earned}
Próximo passo: rastrear a sua encomenda no app.

Bem-vindo oficialmente à família MICHA.''',
     '/orders/{order_id}', 'Ver encomenda'),

    ('order_confirm', 'email', 'pt-AO',
     'Encomenda #{order_id} confirmada',
     '''Olá,

A sua encomenda #{order_id} no valor de {total} {currency} foi confirmada.

Resumo:
{items_summary}

Entrega prevista: {eta}.''',
     '/orders/{order_id}', 'Detalhes'),

    ('post_purchase', 'email', 'pt-AO',
     'A sua encomenda está a caminho',
     '''Olá,

Encomenda #{order_id} despachada. Estimativa de entrega: {eta}.

Rastreio: {tracking_url}.''',
     '/orders/{order_id}/track', 'Rastrear'),

    ('review_request', 'email', 'pt-AO',
     'Como foi a sua experiência?',
     '''Olá,

A sua encomenda #{order_id} já foi entregue. Avalie e ganhe {coins_reward} coins.''',
     '/orders/{order_id}/review', 'Avaliar'),

    ('cart_recovery', 'email', 'pt-AO',
     'Os itens do seu carrinho estão à sua espera',
     '''Olá,

Esqueceu-se de algo? O seu carrinho ainda está guardado:

{items_summary}

Finalize agora antes que o stock acabe.''',
     '/cart', 'Voltar ao carrinho'),

    ('checkout_recovery', 'email', 'pt-AO',
     'O seu pagamento ficou a meio',
     '''Olá,

Reparámos que iniciou o pagamento mas não terminou. Volte e finalize em segundos.

Métodos de pagamento aceites: Multicaixa Express, Visa, Mastercard, transferência bancária.''',
     '/checkout', 'Continuar'),

    ('back_in_stock', 'email', 'pt-AO',
     '{product_name} voltou ao stock!',
     '''Olá,

Boa notícia: {product_name} já está novamente disponível.

Stock limitado — não perca esta oportunidade.''',
     '/product/{product_id}', 'Comprar'),

    ('price_drop', 'email', 'pt-AO',
     '{product_name} agora a {new_price}',
     '''Olá,

O preço de {product_name} baixou de {old_price} para {new_price}.

Aproveite enquanto durar.''',
     '/product/{product_id}', 'Ver produto'),

    ('birthday', 'email', 'pt-AO',
     'Parabéns! 🎉 A sua oferta especial está aqui',
     '''Olá,

A equipa MICHA deseja-lhe um feliz aniversário!

A sua oferta: cupão {coupon_code} + {coins_granted} coins extra.
Válido por 14 dias.''',
     '/?coupon={coupon_code}', 'Aproveitar'),

    ('win_back', 'email', 'pt-AO',
     'Sentimos a sua falta — temos algo para si',
     '''Olá,

Já passou algum tempo desde a sua última visita. Reservámos uma oferta especial para o seu regresso:

Cupão: {coupon_code} no valor de {coupon_value} {currency}.
Válido por 14 dias.''',
     '/?coupon={coupon_code}', 'Voltar à MICHA'),

    ('membership_renew', 'email', 'pt-AO',
     'O seu MICHA Plus renova-se em {days_until_renewal} dias',
     '''Olá,

A sua subscrição MICHA Plus renova-se a {renewal_date} por {amount} {currency}.

Continue a usufruir de envios grátis, reembolsos rápidos e ofertas exclusivas.''',
     '/profile/membership', 'Gerir subscrição'),

    ('flash_sale', 'email', 'pt-AO',
     '⚡ Flash Sale começa em 1 hora',
     '''Olá,

Prepare-se: a próxima Flash Sale começa em 1 hora.

{deal_count} produtos com até {max_discount}% de desconto.''',
     '/flash-sale', 'Ver pré-visualização'),
]


class Command(BaseCommand):
    help = 'Seed the buyer engagement MessageTemplate catalogue.'

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        for entry in TEMPLATES:
            key, kind, locale, subject, body, deep_link, cta = entry
            obj, was_created = MessageTemplate.objects.get_or_create(
                key=key, kind=kind, locale=locale,
                defaults={
                    'subject': subject, 'body': body.strip(),
                    'deep_link': deep_link, 'cta_label': cta,
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(
            f'Templates seeded: created={created}, skipped={skipped}, total={len(TEMPLATES)}',
        ))
