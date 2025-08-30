from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Portfolio


class PortfolioHistoryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass")

    def test_detail_history_data_shows_current_value_without_snapshots(self):
        portfolio = Portfolio.objects.create(user=self.user, name="Test Portfolio", cash_balance=1234.56)
        self.client.force_login(self.user)
        url = reverse("portfolios:portfolio-detail", args=[portfolio.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        history = response.context["history_data"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["value"], portfolio.cash_balance)
        self.assertEqual(history[0]["date"], timezone.now().date().isoformat())

    def test_history_endpoint_returns_current_value_without_snapshots(self):
        portfolio = Portfolio.objects.create(user=self.user, name="API Portfolio", cash_balance=500.0)
        self.client.force_login(self.user)
        url = reverse("portfolios:portfolio-history", args=[portfolio.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["value"], portfolio.cash_balance)
