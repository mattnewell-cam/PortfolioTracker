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
        self.assertTrue(Portfolio.objects.filter(user__username='newuser').exists())
