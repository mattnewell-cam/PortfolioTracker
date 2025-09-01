from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('portfolios', '0014_portfoliosnapshot_benchmark_values'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PortfolioFollower',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('follower', models.ForeignKey(on_delete=models.CASCADE, related_name='followed_portfolios', to=settings.AUTH_USER_MODEL)),
                ('portfolio', models.ForeignKey(on_delete=models.CASCADE, related_name='followers', to='portfolios.portfolio')),
            ],
            options={
                'unique_together': {('portfolio', 'follower')},
            },
        ),
    ]
