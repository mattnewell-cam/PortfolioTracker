from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest.mock import Mock, patch
import pandas as pd
from django.utils import timezone

from .models import Portfolio, Order, PortfolioSnapshot
from .constants import BENCHMARK_CHOICES
from .views import build_portfolio_context


class RegistrationTests(TestCase):
    def test_registration_redirects_to_verification(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newuser',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
                'substack_name': 'Example Stack',
                'substack_url': 'https://example.substack.com',
            },
        )
        self.assertRedirects(response, reverse('verify-substack'))
        self.assertFalse(User.objects.filter(username='newuser').exists())

    @patch('core.views.requests.get')
    def test_substack_verification_creates_user(self, mock_get):
        self.client.post(
            reverse('register'),
            {
                'username': 'newuser',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
                'substack_name': 'Example Stack',
                'substack_url': 'https://example.substack.com',
            },
        )
        nonce = self.client.session['pending_user']['nonce']
        mock_resp = Mock()
        mock_resp.text = f"about page with {nonce}"
        mock_get.return_value = mock_resp

        response = self.client.post(reverse('verify-substack'))
        self.assertRedirects(response, reverse('portfolios:portfolio-detail'))
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertTrue(
            Portfolio.objects.filter(
                user__username='newuser',
                substack_url='https://example.substack.com',
                name='Example Stack',
            ).exists()
        )

    def test_duplicate_substack_url_not_allowed(self):
        user = User.objects.create_user('existing', password='pass')
        Portfolio.objects.create(
            user=user,
            name='Existing Portfolio',
            substack_url='https://example.substack.com',
        )
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newuser',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
                'substack_name': 'Example Stack',
                'substack_url': 'https://example.substack.com',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already linked')
        self.assertFalse(User.objects.filter(username='newuser').exists())
        self.assertNotIn('pending_user', self.client.session)


class PublicPortfolioTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.owner,
            name='Owner Portfolio',
            substack_url='https://owner.substack.com',
        )

    def test_lookup_redirects_to_public_detail(self):
        response = self.client.post(
            reverse('portfolios:portfolio-lookup'),
            {'substack_url': 'https://owner.substack.com'}
        )
        self.assertRedirects(
            response,
            reverse('portfolios:portfolio-public-detail', args=[self.portfolio.pk])
        )

    def test_public_detail_hides_order_link_for_non_owner(self):
        response = self.client.get(
            reverse('portfolios:portfolio-public-detail', args=[self.portfolio.pk])
        )
        self.assertContains(response, 'Owner Portfolio')
        self.assertNotContains(response, 'Place Buy/Sell Order')

    def test_lookup_invalid_shows_error(self):
        response = self.client.post(
            reverse('portfolios:portfolio-lookup'),
            {'substack_url': 'https://unknown.substack.com'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No portfolio found')


class PrivatePortfolioTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.owner,
            name='Private Portfolio',
            substack_url='https://private.substack.com',
            is_private=True,
            holdings={'AAPL': 1},
            cash_balance=1000,
        )
        Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            side='BUY',
            quantity=1,
            price_executed=100,
            currency='USD',
            fx_rate=1.0,
        )

    def test_public_view_hides_positions_and_orders(self):
        response = self.client.get(
            reverse('portfolios:portfolio-public-detail', args=[self.portfolio.pk])
        )
        self.assertContains(response, 'Value Over Time')
        self.assertContains(response, 'This portfolio is private')
        self.assertNotContains(response, 'Current Holdings')
        self.assertNotContains(response, 'Order History')
        self.assertEqual(response.context['positions'], [])
        self.assertEqual(response.context['orders_data'], [])


class PortfolioPrivacyToggleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Toggle Portfolio',
            substack_url='https://toggle.substack.com',
            is_private=False,
        )

    def test_toggle_button_visible_to_owner(self):
        self.client.login(username='owner', password='pass')
        response = self.client.get(reverse('portfolios:portfolio-detail'))
        self.assertContains(response, 'Make Portfolio Private')

    def test_toggle_changes_privacy(self):
        self.client.login(username='owner', password='pass')
        response = self.client.post(reverse('portfolios:portfolio-toggle-privacy'))
        self.assertRedirects(response, reverse('portfolios:portfolio-detail'))
        self.portfolio.refresh_from_db()
        self.assertTrue(self.portfolio.is_private)

    def test_toggle_button_hidden_from_public_view(self):
        other = User.objects.create_user('viewer', password='pass')
        self.client.login(username='viewer', password='pass')
        response = self.client.get(
            reverse('portfolios:portfolio-public-detail', args=[self.portfolio.pk])
        )
        self.assertNotContains(response, 'Make Portfolio')


class BenchmarkContextTests(TestCase):
    @patch('portfolios.views.yf.Ticker')
    def test_context_includes_all_benchmarks_and_defaults(self, mock_ticker):
        mock_instance = Mock()
        mock_instance.history.return_value = pd.DataFrame({
            'Close': [100.0]
        }, index=[pd.Timestamp('2024-01-01')])
        mock_instance.fast_info = {'currency': 'USD'}
        mock_ticker.return_value = mock_instance

        user = User.objects.create_user('bench', password='pass')
        portfolio = Portfolio.objects.create(
            user=user,
            name='Bench Portfolio',
            substack_url='https://bench.substack.com',
            benchmarks=[BENCHMARK_CHOICES[0][0], BENCHMARK_CHOICES[1][0]],
        )
        PortfolioSnapshot.objects.create(
            portfolio=portfolio,
            timestamp=timezone.now(),
            total_value=100000,
        )

        ctx = build_portfolio_context(portfolio)
        self.assertEqual(ctx['default_benchmarks'], portfolio.benchmarks)
        self.assertEqual(len(ctx['benchmark_data']), len(BENCHMARK_CHOICES))


class ExplorePageTests(TestCase):
    def setUp(self):
        user1 = User.objects.create_user('alpha', password='pass')
        user2 = User.objects.create_user('beta', password='pass')
        self.port1 = Portfolio.objects.create(
            user=user1,
            name='Alpha Stack',
            substack_url='https://alpha.substack.com',
            is_private=False,
        )
        self.port2 = Portfolio.objects.create(
            user=user2,
            name='Beta Stack',
            substack_url='https://beta.substack.com',
            is_private=True,
        )
        PortfolioSnapshot.objects.create(
            portfolio=self.port1,
            timestamp=timezone.now(),
            total_value=1000,
        )
        PortfolioSnapshot.objects.create(
            portfolio=self.port2,
            timestamp=timezone.now(),
            total_value=2000,
        )

    def test_explore_lists_all_portfolios(self):
        response = self.client.get(reverse('portfolios:portfolio-explore'))
        self.assertContains(response, 'Alpha Stack')
        self.assertContains(response, 'Beta Stack')

    def test_search_filters_portfolios(self):
        response = self.client.get(reverse('portfolios:portfolio-explore'), {'q': 'beta'})
        self.assertContains(response, 'Beta Stack')
        self.assertNotContains(response, 'Alpha Stack')

    def test_explore_uses_snapshot_without_fetching_quotes(self):
        user3 = User.objects.create_user('gamma', password='pass')
        Portfolio.objects.create(
            user=user3,
            name='Gamma Stack',
            holdings={'AAPL': 5},
        )
        with patch('portfolios.views.get_quote') as mock_get_quote:
            self.client.get(reverse('portfolios:portfolio-explore'))
        mock_get_quote.assert_not_called()

