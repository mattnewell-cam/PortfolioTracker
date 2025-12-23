import random
import secrets
import uuid

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
    if Portfolio.objects.filter(user=request.user, is_deleted=False).exists():
        return redirect("portfolios:portfolio-detail")
    if request.method == "POST":
        form = PortfolioSetupForm(request.POST, user=request.user)
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
        form = PortfolioSetupForm(user=request.user)
    return render(request, "registration/portfolio_setup.html", {"form": form})


@login_required
def verify_portfolio(request):
    pending = request.session.get("pending_portfolio")
    if not pending:
        return redirect("add-portfolio")

    existing_portfolio = Portfolio.objects.filter(user=request.user).first()
    if existing_portfolio and not existing_portfolio.is_deleted:
        return redirect("portfolios:portfolio-detail")

    if request.method == "POST":
        conflict_qs = Portfolio.objects.filter(
            substack_url=pending["substack_url"]
        )
        if existing_portfolio:
            conflict_qs = conflict_qs.exclude(pk=existing_portfolio.pk)
        if conflict_qs.exists():
            messages.error(
                request,
                "Substack already linked to another trackstack account. If you have lost access to your previous trackstack account, email support@trackstack.uk",
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

                host = pending["substack_url"].split("://")[1]
                url_tag_base = host.split(".substack")[0]
                url_tag = url_tag_base
                counter = 1
                while Portfolio.objects.filter(url_tag=url_tag).exclude(
                    pk=getattr(existing_portfolio, "pk", None)
                ).exists():
                    url_tag = f"{url_tag_base}-{counter}"
                    counter += 1

                if existing_portfolio and existing_portfolio.is_deleted:
                    if existing_portfolio.substack_url == pending["substack_url"]:
                        existing_portfolio.name = title
                        existing_portfolio.short_description = subtitle
                        existing_portfolio.benchmarks = pending["benchmarks"]
                        existing_portfolio.is_deleted = False
                        existing_portfolio.deleted_at = None
                        existing_portfolio.save(
                            update_fields=[
                                "name",
                                "short_description",
                                "benchmarks",
                                "is_deleted",
                                "deleted_at",
                            ]
                        )
                    else:
                        existing_portfolio.orders.all().delete()
                        existing_portfolio.snapshots.all().delete()
                        existing_portfolio.followers.all().delete()
                        existing_portfolio.allowed_emails.all().delete()
                        existing_portfolio.holdings = {}
                        existing_portfolio.cash_balance = Portfolio._meta.get_field("cash_balance").default
                        existing_portfolio.name = title
                        existing_portfolio.short_description = subtitle
                        existing_portfolio.substack_url = pending["substack_url"]
                        existing_portfolio.url_tag = url_tag
                        existing_portfolio.benchmarks = pending["benchmarks"]
                        existing_portfolio.is_private = False
                        existing_portfolio.is_deleted = False
                        existing_portfolio.deleted_at = None
                        existing_portfolio.save()
                else:
                    Portfolio.objects.create(
                        user=request.user,
                        name=title,
                        substack_url=pending["substack_url"],
                        url_tag=url_tag or uuid.uuid4(),
                        benchmarks=pending["benchmarks"],
                        short_description=subtitle,
                    )
                display_name = pending["display_name"]
                if request.user.first_name != display_name:
                    request.user.first_name = display_name
                    request.user.save(update_fields=["first_name"])
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
