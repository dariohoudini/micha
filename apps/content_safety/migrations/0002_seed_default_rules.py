from django.db import migrations


def seed(apps, schema_editor):
    ScanRule = apps.get_model('content_safety', 'ScanRule')
    seeds = [
        ('phone_local_ao', r'9[2-9]\d\s?\d{3}\s?\d{3}', 'pii', 'block',
         'Não é permitido partilhar números de telefone no chat.'),
        ('phone_intl_ao',  r'\+244\s?\d{3}\s?\d{3}\s?\d{3}', 'pii', 'block',
         'Não é permitido partilhar números de telefone.'),
        ('whatsapp_mention', r'wh?at?s?app|zap\s*:?\s*\d', 'scam', 'block',
         'WhatsApp não é permitido — comuniquem dentro da MICHA.'),
        ('email_address',  r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
         'pii', 'warn',
         'Lembrete: mantenham a comunicação dentro da plataforma.'),
        ('iban',           r'iban\s*:?\s*[A-Z]{2}\d{2}', 'scam', 'block',
         'Não solicitem transferências fora da plataforma.'),
        ('multicaixa',     r'multicaixa\s*(express)?\s*:\s*\d', 'scam', 'block',
         'Pagamentos só pela MICHA Express.'),
        ('external_link',  r'https?://(?!micha\.ao)\S+', 'phishing', 'hide',
         'Links externos foram ocultados.'),
        ('url_shortener',  r'bit\.ly|tinyurl|shorturl', 'phishing', 'block',
         'Links encurtados não são permitidos.'),
        ('pay_outside',    r'pague?\s*(fora|directo|direct)', 'scam', 'warn',
         'Sinalização: tentativa de pagamento fora da plataforma.'),
    ]
    for name, pattern, category, severity, msg in seeds:
        ScanRule.objects.get_or_create(
            name=name,
            defaults={
                'pattern': pattern, 'category': category,
                'severity': severity, 'user_message': msg,
                'description': f'Bootstrap rule: {name}',
            },
        )


def unseed(apps, schema_editor):
    ScanRule = apps.get_model('content_safety', 'ScanRule')
    ScanRule.objects.filter(description__startswith='Bootstrap rule:').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('content_safety', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]
