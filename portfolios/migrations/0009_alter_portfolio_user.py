from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('portfolios', '0008_portfolio_benchmarks'),
    ]

    operations = [
        migrations.AlterField(
            model_name='portfolio',
            name='user',
            field=models.OneToOneField(on_delete=models.CASCADE, related_name='portfolio', to=settings.AUTH_USER_MODEL),
        ),
    ]
