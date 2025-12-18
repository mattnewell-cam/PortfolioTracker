import random
import secrets

import requests
import feedparser
from urllib.parse import urlparse, urlunparse
from django.contrib import messages
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from portfolios.models import Portfolio

from .email import send_email
from .forms import (
    EmailRegistrationForm,
    EmailVerificationForm,
    PortfolioSetupForm,
)


def register(request):
    """Start registration by collecting email and password."""
    if request.method == "POST":
        form = EmailRegistrationForm(request.POST)
        if form.is_valid():
            code = f"{random.randint(0, 999999):06d}"
            request.session["pending_registration"] = {
                "email": form.cleaned_data["email"],
                "password": form.cleaned_data["password1"],
                "code": code,
            }
            send_email(
                "verify@trackstack.uk",
                "Verify your account",
                f"Your verification code is {code}",
                [form.cleaned_data["email"]],
                fail_silently=True,
            )
            print("Sending verification email.")
            return redirect("verify-email")
    else:
        form = EmailRegistrationForm()
    return render(request, "registration/register.html", {"form": form})


def verify_email(request):
    pending = request.session.get("pending_registration")
    if not pending:
        return redirect("register")

    if request.method == "POST":
        form = EmailVerificationForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["code"] == pending["code"]:
                User = get_user_model()
                user = User.objects.create_user(
                    pending["email"], email=pending["email"], password=pending["password"]
                )
                login(request, user)
                del request.session["pending_registration"]
                return redirect("add-portfolio")
            else:
                form.add_error("code", "Invalid verification code.")
    else:
        form = EmailVerificationForm()
    return render(request, "registration/verify_email.html", {"form": form})


@login_required
def add_portfolio(request):
    if Portfolio.objects.filter(user=request.user).exists():
        return redirect("portfolios:portfolio-detail")
    if request.method == "POST":
        form = PortfolioSetupForm(request.POST)
        if form.is_valid():
            nonce = secrets.token_hex(12)
            request.session["pending_portfolio"] = {
                "display_name": form.cleaned_data["display_name"],
                "substack_url": form.cleaned_data["substack_url"],
                "benchmarks": form.cleaned_data["benchmarks"],
                "nonce": nonce,
            }
            return redirect("verify-portfolio")
    else:
        form = PortfolioSetupForm()
    return render(request, "registration/portfolio_setup.html", {"form": form})


@login_required
def verify_portfolio(request):
    pending = request.session.get("pending_portfolio")
    if not pending:
        return redirect("add-portfolio")

    if request.method == "POST":
        if Portfolio.objects.filter(substack_url=pending["substack_url"]).exists():
            messages.error(
                request, "This Substack URL is already linked to another account."
            )
            del request.session["pending_portfolio"]
            return redirect("add-portfolio")

        parsed_url = urlparse(pending["substack_url"])
        host = parsed_url.hostname or ""
        if host != "substack.com" and not host.endswith(".substack.com"):
            messages.error(request, "Invalid Substack URL.")
            del request.session["pending_portfolio"]
            return redirect("add-portfolio")
        substack_about = urlunparse(
            parsed_url._replace(path="/about", params="", query="", fragment="")
        )
        try:
            resp = requests.get(substack_about, timeout=5)
            if pending["nonce"] in resp.text:
                feed_url = urlunparse(
                    parsed_url._replace(path="/feed", params="", query="", fragment="")
                )
                subtitle = ""
                title = pending["display_name"]
                try:
                    feed = feedparser.parse(feed_url)
                    title = feed.feed.get("title") or title
                    subtitle = feed.feed.get("subtitle") or feed.feed.get("description") or ""
                except Exception:
                    pass

                Portfolio.objects.create(
                    user=request.user,
                    name=title,
                    substack_url=pending["substack_url"],
                    benchmarks=pending["benchmarks"],
                    short_description=subtitle,
                )
                del request.session["pending_portfolio"]
                return redirect("portfolios:portfolio-detail")
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
