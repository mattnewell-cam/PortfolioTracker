from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest.mock import Mock, patch
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from io import BytesIO
import importlib
from unittest import skipUnless

from .models import Portfolio, Order, PortfolioSnapshot, PortfolioAllowedEmail
from decimal import Decimal
from .constants import BENCHMARK_CHOICES
from .views import build_portfolio_context
import pandas as pd
import pytz


class RegistrationTests(TestCase):
    def test_registration_redirects_to_email_verification(self):
        response = self.client.post(
            reverse('register'),
            {
                'email': 'new@example.com',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
            },
        )
        self.assertRedirects(response, reverse('verify-email'))
        self.assertFalse(User.objects.filter(username='new@example.com').exists())
        self.assertIn('pending_registration', self.client.session)

    def test_email_verification_creates_user(self):
        self.client.post(
            reverse('register'),
            {
                'email': 'new@example.com',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
            },
        )
        code = self.client.session['pending_registration']['code']
        response = self.client.post(reverse('verify-email'), {'code': code})
        self.assertRedirects(response, reverse('add-portfolio'))
        self.assertTrue(User.objects.filter(username='new@example.com').exists())

    def test_duplicate_email_not_allowed(self):
        User.objects.create_user('new@example.com', password='pass')
        response = self.client.post(
            reverse('register'),
            {
                'email': 'new@example.com',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already registered')
        self.assertNotIn('pending_registration', self.client.session)

    @patch('core.views.feedparser.parse')
    @patch('core.views.requests.get')
    def test_portfolio_creation_flow(self, mock_get, mock_parse):
        self.client.post(
            reverse('register'),
            {
                'email': 'new@example.com',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
            },
        )
        code = self.client.session['pending_registration']['code']
        self.client.post(reverse('verify-email'), {'code': code})

        self.client.post(
            reverse('add-portfolio'),
            {
                'display_name': 'Example',
                'substack_url': 'https://example.substack.com',
                'benchmarks': [BENCHMARK_CHOICES[0][0]],
            },
        )
        nonce = self.client.session['pending_portfolio']['nonce']
        mock_about = Mock()
        mock_about.text = f"about page with {nonce}"
        mock_feed = Mock(feed={'title': 'Example Feed', 'subtitle': 'Short desc'})
        mock_get.return_value = mock_about
        mock_parse.return_value = mock_feed

        response = self.client.post(reverse('verify-portfolio'))
        self.assertRedirects(response, reverse('portfolios:portfolio-detail'))
        self.assertTrue(
            Portfolio.objects.filter(
                user__username='new@example.com',
                substack_url='https://example.substack.com',
                name='Example Feed',
                short_description='Short desc',
                benchmarks=[BENCHMARK_CHOICES[0][0]],
            ).exists()
        )

    def test_duplicate_substack_url_not_allowed(self):
        existing = User.objects.create_user('existing@example.com', password='pass')
        Portfolio.objects.create(
            user=existing,
            name='Existing',
            substack_url='https://example.substack.com',
        )
        self.client.post(
            reverse('register'),
            {
                'email': 'new@example.com',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
            },
        )
        code = self.client.session['pending_registration']['code']
        self.client.post(reverse('verify-email'), {'code': code})
        response = self.client.post(
            reverse('add-portfolio'),
            {
                'display_name': 'New',
                'substack_url': 'https://example.substack.com',
                'benchmarks': [BENCHMARK_CHOICES[0][0]],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already linked')
        self.assertNotIn('pending_portfolio', self.client.session)


class DefaultRedirectTests(TestCase):
    def test_root_redirects_to_login_when_anonymous(self):
        response = self.client.get('/', follow=True)
        self.assertRedirects(response, '/accounts/login/?next=/portfolios/')

    def test_root_shows_empty_portfolio_for_new_user(self):
        user = User.objects.create_user('anon@example.com', password='pass')
        self.client.login(username='anon@example.com', password='pass')
        response = self.client.get('/', follow=True)
        self.assertContains(response, 'Add Portfolio')


class PublicPortfolioTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.owner,
            name='Owner Portfolio',
            substack_url='https://owner.substack.com',
        )

    def test_public_detail_hides_order_link_for_non_owner(self):
        response = self.client.get(
            reverse('portfolios:portfolio-public-detail', kwargs={'tag': self.portfolio.url_tag})
        )
        self.assertContains(response, 'Owner Portfolio')
        self.assertNotContains(response, 'id_symbol')


class PortfolioExploreTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            'owner@example.com', password='pass', first_name='Owner Name'
        )
        self.portfolio = Portfolio.objects.create(
            user=self.owner,
            name='Owner Portfolio',
            substack_url='https://owner.substack.com',
        )

    def test_display_name_shown_on_card(self):
        response = self.client.get(reverse('portfolios:portfolio-explore'))
        self.assertContains(response, 'Owner Name')


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
            reverse('portfolios:portfolio-public-detail', kwargs={'tag': self.portfolio.url_tag})
        )
        self.assertContains(response, 'Value Over Time')
        self.assertContains(response, 'This portfolio is private')
        self.assertNotContains(response, 'Current Holdings')
        self.assertNotContains(response, 'Order History')
        self.assertEqual(response.context['positions'], [])
        self.assertEqual(response.context['orders_data'], [])


class AllowListTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner@example.com', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.owner,
            name='Private',
            substack_url='https://allow.substack.com',
            is_private=True,
            holdings={'AAPL': 1},
        )
        PortfolioAllowedEmail.objects.create(
            portfolio=self.portfolio, email='viewer@example.com'
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

    def test_allowed_user_can_view_details_and_follow(self):
        viewer = User.objects.create_user('viewer@example.com', password='pass')
        self.client.login(username='viewer@example.com', password='pass')
        response = self.client.get(
            reverse('portfolios:portfolio-public-detail', kwargs={'tag': self.portfolio.url_tag})
        )
        self.assertFalse(response.context['private_view'])
        self.assertNotEqual(response.context['positions'], [])
        self.client.post(
            reverse('portfolios:portfolio-follow-toggle', kwargs={'tag': self.portfolio.url_tag})
        )
        self.assertTrue(
            self.portfolio.followers.filter(follower=viewer).exists()
        )

    def test_unlisted_user_cannot_follow(self):
        other = User.objects.create_user('other@example.com', password='pass')
        self.client.login(username='other@example.com', password='pass')
        self.client.post(
            reverse('portfolios:portfolio-follow-toggle', kwargs={'tag': self.portfolio.url_tag})
        )
        self.assertFalse(
            self.portfolio.followers.filter(follower=other).exists()
        )

    def test_csv_upload_adds_all_emails(self):
        self.client.login(username='owner@example.com', password='pass')
        csv_data = "\ufeffalpha@example.com\nbeta@example.com\n".encode("utf-8")
        upload = SimpleUploadedFile(
            "emails.csv", csv_data, content_type="text/csv"
        )
        self.client.post(
            reverse('portfolios:portfolio-allow-list'),
            {'action': 'upload', 'file': upload},
        )
        self.assertTrue(
            PortfolioAllowedEmail.objects.filter(
                portfolio=self.portfolio, email='alpha@example.com'
            ).exists()
        )
        self.assertTrue(
            PortfolioAllowedEmail.objects.filter(
                portfolio=self.portfolio, email='beta@example.com'
            ).exists()
        )

    @skipUnless(importlib.util.find_spec("openpyxl"), "openpyxl not installed")
    def test_excel_upload_adds_all_emails(self):
        self.client.login(username='owner@example.com', password='pass')
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(['gamma@example.com'])
        ws.append(['delta@example.com'])
        stream = BytesIO()
        wb.save(stream)
        stream.seek(0)
        upload = SimpleUploadedFile(
            "emails.xlsx",
            stream.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.client.post(
            reverse('portfolios:portfolio-allow-list'),
            {'action': 'upload', 'file': upload},
        )
        self.assertTrue(
            PortfolioAllowedEmail.objects.filter(
                portfolio=self.portfolio, email='gamma@example.com'
            ).exists()
        )
        self.assertTrue(
            PortfolioAllowedEmail.objects.filter(
                portfolio=self.portfolio, email='delta@example.com'
            ).exists()
        )

    def test_delete_single_email(self):
        self.client.login(username='owner@example.com', password='pass')
        email = PortfolioAllowedEmail.objects.create(
            portfolio=self.portfolio, email='trash@example.com'
        )
        self.client.post(
            reverse('portfolios:portfolio-allow-list'),
            {'action': 'delete', 'id': email.id},
        )
        self.assertFalse(
            PortfolioAllowedEmail.objects.filter(id=email.id).exists()
        )

    def test_delete_all_emails(self):
        self.client.login(username='owner@example.com', password='pass')
        PortfolioAllowedEmail.objects.create(
            portfolio=self.portfolio, email='other@example.com'
        )
        self.client.post(
            reverse('portfolios:portfolio-allow-list'),
            {'action': 'delete_all'},
        )
        self.assertEqual(self.portfolio.allowed_emails.count(), 0)


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
        self.assertContains(response, 'Make Private')

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
            reverse('portfolios:portfolio-public-detail', kwargs={'tag': self.portfolio.url_tag})
        )
        self.assertNotContains(response, 'Make Portfolio')


class BenchmarkContextTests(TestCase):
    def test_context_includes_all_benchmarks_and_defaults(self):
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
            benchmark_values={t: 100.0 for t, _ in BENCHMARK_CHOICES},
        )

        ctx = build_portfolio_context(portfolio)
        self.assertEqual(ctx['default_benchmarks'], portfolio.benchmarks)
        self.assertEqual(len(ctx['benchmark_data']), len(BENCHMARK_CHOICES))
        for bm in ctx['benchmark_data']:
            if bm['data']:
                self.assertEqual(bm['data'][0]['price_usd'], 100000.0)


class AllocationContextTests(TestCase):
    @patch('portfolios.views.get_quote')
    def test_allocations_include_cash(self, mock_quote):
        user = User.objects.create_user('alloc', password='pass')
        portfolio = Portfolio.objects.create(
            user=user,
            name='Alloc Portfolio',
            substack_url='https://alloc.substack.com',
            holdings={'AAPL': 1},
            cash_balance=1000,
        )
        mock_quote.return_value = {
            'price': 100,
            'currency': 'USD',
            'fx_rate': 1,
        }
        ctx = build_portfolio_context(portfolio)
        pos = ctx['positions'][0]
        expected_pos = Decimal('100') / Decimal('1100') * 100
        expected_cash = Decimal('1000') / Decimal('1100') * 100
        self.assertEqual(pos['allocation'], expected_pos)
        self.assertEqual(ctx['cash_allocation'], expected_cash)


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


class FollowPortfolioTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pass')
        self.viewer = User.objects.create_user('viewer', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.owner,
            name='Owner Portfolio',
            substack_url='https://owner2.substack.com',
        )

    def test_follow_requires_login(self):
        url = reverse('portfolios:portfolio-follow-toggle', kwargs={'tag': self.portfolio.url_tag})
        response = self.client.post(url)
        self.assertRedirects(response, f'/accounts/login/?next={url}')

    def test_follow_and_unfollow(self):
        self.client.login(username='viewer', password='pass')
        url = reverse('portfolios:portfolio-follow-toggle', kwargs={'tag': self.portfolio.url_tag})
        self.client.post(url)
        self.assertTrue(
            self.portfolio.followers.filter(follower=self.viewer).exists()
        )
        self.client.post(url)
        self.assertFalse(
            self.portfolio.followers.filter(follower=self.viewer).exists()
        )

    @patch('portfolios.views.get_quote')
    @patch('portfolios.views.send_email')
    def test_follower_notified_on_trade(self, mock_send, mock_quote):
        mock_quote.return_value = {
            'price': 100,
            'bid': 100,
            'ask': 100,
            'traded_today': True,
            'currency': 'USD',
            'fx_rate': 1,
            'market_state': 'REGULAR',
        }
        # viewer follows portfolio
        self.client.login(username='viewer', password='pass')
        follow_url = reverse('portfolios:portfolio-follow-toggle', kwargs={'tag': self.portfolio.url_tag})
        self.client.post(follow_url)
        self.client.logout()
        # owner places trade
        self.client.login(username='owner', password='pass')
        self.client.post(
            reverse('portfolios:order-create'),
            {'symbol': 'AAPL', 'side': 'BUY', 'quantity': 1},
        )
        mock_send.assert_called()


class OrderSymbolTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('symuser', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Sym Portfolio',
            substack_url='https://sym.substack.com',
        )

    def test_symbol_saved_uppercase(self):
        Order.objects.create(
            portfolio=self.portfolio,
            symbol='aapl',
            side='BUY',
            quantity=1,
            price_executed=100,
            currency='usd',
            fx_rate=1.0,
        )
        order = self.portfolio.orders.first()
        self.assertEqual(order.symbol, 'AAPL')
        ctx = build_portfolio_context(self.portfolio)
        self.assertEqual(ctx['orders_data'][0]['symbol'], 'AAPL')


class OrderFxRateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('fxuser', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='FX Portfolio',
            substack_url='https://fx.substack.com',
        )

    def test_fx_rate_precision_for_gbp_pence(self):
        fx_input = Decimal('0.01353216648')
        expected = fx_input.quantize(Decimal('0.0000000001'))
        Order.objects.create(
            portfolio=self.portfolio,
            symbol='vod.l',
            side='BUY',
            quantity=1,
            price_executed=100,
            currency='GBp',
            fx_rate=fx_input,
        )
        order = self.portfolio.orders.first()
        self.assertEqual(order.fx_rate, expected)
        ctx = build_portfolio_context(self.portfolio)
        self.assertEqual(ctx['orders_data'][0]['fx_rate'], expected)


class AccountDetailsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'user@example.com', email='user@example.com', password='pass', first_name='User'
        )
        self.client.login(username='user@example.com', password='pass')

    def test_account_details_shows_display_name(self):
        response = self.client.get(reverse('portfolios:account-details'))
        self.assertContains(response, 'value="User"')

    def test_change_display_name(self):
        response = self.client.post(
            reverse('portfolios:account-details'),
            {'display_name': 'New'},
        )
        self.assertRedirects(response, reverse('portfolios:account-details'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'New')
        self.assertNotIn('pending_email_change', self.client.session)

    @patch('portfolios.views.send_email')
    def test_change_email_requires_verification(self, mock_send):
        response = self.client.post(
            reverse('portfolios:account-details'),
            {'display_name': 'User', 'email': 'new@example.com'},
        )
        self.assertRedirects(response, reverse('portfolios:account-verify-email'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'user@example.com')
        self.assertIn('pending_email_change', self.client.session)
        self.assertEqual(
            self.client.session['pending_email_change']['new_email'], 'new@example.com'
        )

    @patch('portfolios.views.send_email')
    def test_verify_email_change_updates_email(self, mock_send):
        self.client.post(
            reverse('portfolios:account-details'),
            {'display_name': 'User', 'email': 'new@example.com'},
        )
        code = self.client.session['pending_email_change']['code']
        response = self.client.post(
            reverse('portfolios:account-verify-email'), {'code': code}
        )
        self.assertRedirects(response, reverse('portfolios:account-details'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')
        self.assertNotIn('pending_email_change', self.client.session)


class SnapshotAdjustmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('snap', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Snap Portfolio',
            substack_url='https://snap.substack.com',
            holdings={'AAPL': 2},
            cash_balance=Decimal('0'),
        )

    def _run_command(self, ticker, quote, now):
        with patch('portfolios.management.commands.take_snapshots.sys.exit'), \
             patch('portfolios.management.commands.take_snapshots.yf.Ticker', return_value=ticker), \
             patch('portfolios.management.commands.take_snapshots.get_quotes', return_value={'AAPL': quote}), \
             patch('portfolios.management.commands.take_snapshots.get_quote', return_value=quote), \
             patch('portfolios.management.commands.take_snapshots.get_benchmark_prices_usd', return_value={}), \
             patch('portfolios.management.commands.take_snapshots.timezone.now', return_value=now):
            call_command('take_snapshots')

    def test_take_snapshots_adjusts_holdings_for_splits(self):
        now = timezone.datetime(2024, 5, 1, tzinfo=pytz.UTC)
        splits = pd.Series({pd.Timestamp(now.date()): 2})
        dividends = pd.Series({pd.Timestamp(now.date()): 1})
        ticker = Mock(splits=splits, dividends=dividends)
        quote = {'price': 10, 'fx_rate': 1}
        self._run_command(ticker, quote, now)
        self.portfolio.refresh_from_db()
        self.assertEqual(self.portfolio.holdings['AAPL'], 4)
        snapshot = PortfolioSnapshot.objects.get(portfolio=self.portfolio)
        self.assertEqual(snapshot.total_value, Decimal('44'))

    def test_take_snapshots_credits_recent_dividends(self):
        now = timezone.datetime(2024, 5, 1, tzinfo=pytz.UTC)
        splits = pd.Series(dtype=float)
        dividends = pd.Series({pd.Timestamp(now.date()): 1.5})
        ticker = Mock(splits=splits, dividends=dividends)
        quote = {'price': 10, 'fx_rate': 1}
        self._run_command(ticker, quote, now)
        self.portfolio.refresh_from_db()
        self.assertEqual(self.portfolio.cash_balance, Decimal('3'))
        snapshot = PortfolioSnapshot.objects.get(portfolio=self.portfolio)
        self.assertEqual(snapshot.total_value, Decimal('23'))

    def test_take_snapshots_converts_gbp_dividends_from_pence(self):
        now = timezone.datetime(2024, 5, 1, tzinfo=pytz.UTC)
        splits = pd.Series(dtype=float)
        dividends = pd.Series({pd.Timestamp(now.date()): 150})
        ticker = Mock(splits=splits, dividends=dividends)
        quote = {'price': 10, 'fx_rate': 1, 'native_currency': 'GBp'}

        self._run_command(ticker, quote, now)

        self.portfolio.refresh_from_db()
        # 150 pence dividend = £1.50 per share; holdings of 2 → £3.00 credited
        self.assertEqual(self.portfolio.cash_balance, Decimal('3'))
        snapshot = PortfolioSnapshot.objects.get(portfolio=self.portfolio)
        self.assertEqual(snapshot.total_value, Decimal('23'))


class DeleteSnapshotsCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('deleter', password='pass')
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Delete Portfolio',
            substack_url='https://delete.substack.com',
            holdings={'AAPL': 1},
            cash_balance=Decimal('10'),
        )
        PortfolioSnapshot.objects.create(
            portfolio=self.portfolio,
            timestamp=timezone.now(),
            total_value=Decimal('10'),
            benchmark_values={},
        )

    def test_requires_confirmation_flag(self):
        with self.assertRaises(CommandError):
            call_command('delete_snapshots')

    def test_deletes_snapshots_only(self):
        call_command('delete_snapshots', yes=True)

        self.assertFalse(PortfolioSnapshot.objects.exists())
        self.assertTrue(Portfolio.objects.filter(pk=self.portfolio.url_tag).exists())

    def test_can_scope_to_single_portfolio(self):
        other_user = User.objects.create_user('keeper', password='pass')
        other_portfolio = Portfolio.objects.create(
            user=other_user,
            name='Keep Portfolio',
            substack_url='https://keep.substack.com',
            holdings={'MSFT': 2},
            cash_balance=Decimal('20'),
        )
        PortfolioSnapshot.objects.create(
            portfolio=other_portfolio,
            timestamp=timezone.now(),
            total_value=Decimal('20'),
            benchmark_values={},
        )

        call_command('delete_snapshots', yes=True, portfolio=self.portfolio.url_tag)

        self.assertFalse(PortfolioSnapshot.objects.filter(portfolio=self.portfolio).exists())
        self.assertTrue(PortfolioSnapshot.objects.filter(portfolio=other_portfolio).exists())
