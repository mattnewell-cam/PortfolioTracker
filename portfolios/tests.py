from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Portfolio


class RegistrationTests(TestCase):
    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'strong-pass-123',
            'password2': 'strong-pass-123',
        })
        self.assertRedirects(response, reverse('portfolios:portfolio-detail'))
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertTrue(Portfolio.objects.filter(user__username='newuser').exists())
