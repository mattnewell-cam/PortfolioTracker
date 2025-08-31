import secrets

import requests
import feedparser
from urllib.parse import urlparse, urlunparse
from django.contrib import messages
from django.contrib.auth import login, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.conf import settings

from portfolios.models import Portfolio

from .forms import SubstackRegistrationForm


def register(request):
    """Start registration by collecting credentials and Substack URL."""
    if request.method == "POST":
        form = SubstackRegistrationForm(request.POST)
        if form.is_valid():
            nonce = secrets.token_hex(12)  # 24-character nonce
            request.session["pending_user"] = {
                "username": form.cleaned_data["username"],
                "password1": form.cleaned_data["password1"],
                "email": form.cleaned_data["email"],
                "substack_url": form.cleaned_data["substack_url"],
                "benchmarks": form.cleaned_data["benchmarks"],
                "nonce": nonce,
            }
            return redirect("verify-substack")
    else:
        form = SubstackRegistrationForm()
    return render(request, "registration/register.html", {"form": form})


def verify_substack(request):
    """Verify the presence of the nonce on the user's Substack about page."""
    pending = request.session.get("pending_user")
    if not pending:
        return redirect("register")

    if request.method == "POST":
        if Portfolio.objects.filter(substack_url=pending["substack_url"]).exists():
            messages.error(
                request, "This Substack URL is already linked to another account."
            )
            del request.session["pending_user"]
            return redirect("register")

        parsed_url = urlparse(pending["substack_url"])
        host = parsed_url.hostname or ""
        if host != "substack.com" and not host.endswith(".substack.com"):
            messages.error(request, "Invalid Substack URL.")
            del request.session["pending_user"]
            return redirect("register")
        substack_about = urlunparse(
            parsed_url._replace(path="/about", params="", query="", fragment="")
        )
        try:
            resp = requests.get(substack_about, timeout=5)
            if pending["nonce"] in resp.text:
                feed_url = urlunparse(
                    parsed_url._replace(path="/feed", params="", query="", fragment="")
                )
                title = ""
                subtitle = ""
                try:
                    feed = feedparser.parse(feed_url)
                    title = feed.feed.get("title", "")
                    subtitle = feed.feed.get("subtitle") or feed.feed.get("description") or ""
                except Exception:
                    pass

                User = get_user_model()
                user = User.objects.create_user(
                    pending["username"],
                    password=pending["password1"],
                    email=pending["email"],
                    is_active=False,
                )
                Portfolio.objects.create(
                    user=user,
                    name=title or pending["substack_url"],
                    substack_url=pending["substack_url"],
                    benchmarks=pending.get("benchmarks", []),
                    short_description=subtitle,
                )

                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                verify_link = request.build_absolute_uri(
                    reverse("verify-email", args=[uid, token])
                )
                send_mail(
                    "Verify your email",
                    f"Click the link to verify your email: {verify_link}",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
                del request.session["pending_user"]
                return redirect("email-verification-sent")
        except requests.RequestException:
            pass
        messages.error(
            request,
            "Substack verification failed. Ensure the nonce is present on your about page.",
        )

    return render(
        request,
        "registration/verify_substack.html",
        {"nonce": pending["nonce"], "substack_url": pending["substack_url"]},
    )


def email_verification_sent(request):
    return render(request, "registration/email_verification_sent.html")


def verify_email(request, uidb64, token):
    User = get_user_model()
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None

    if user and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        return redirect("portfolios:portfolio-detail")

    return render(request, "registration/verify_email_failed.html")
