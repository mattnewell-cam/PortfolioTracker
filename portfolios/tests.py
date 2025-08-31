from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from unittest.mock import Mock, patch

from .models import Portfolio


class RegistrationTests(TestCase):
    def test_registration_redirects_to_verification(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newuser',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
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
            ).exists()
        )

    def test_duplicate_substack_url_not_allowed(self):
        user = User.objects.create_user('existing', password='pass')
        Portfolio.objects.create(
            user=user,
            name='My Portfolio',
            substack_url='https://example.substack.com',
        )
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newuser',
                'password1': 'strong-pass-123',
                'password2': 'strong-pass-123',
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
