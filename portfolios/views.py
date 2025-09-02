from django.shortcuts import redirect, get_object_or_404, render
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, CreateView, ListView
from django.db.models import Q
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from decimal import Decimal

from core.yfinance_client import get_quote
from .models import Portfolio, Order, PortfolioSnapshot, PortfolioFollower, PortfolioAllowedEmail
from .constants import BENCHMARK_CHOICES
from .forms import PortfolioForm, OrderForm, AllowedEmailForm, AllowedEmailUploadForm
import yfinance as yf
import json
import csv
from io import StringIO

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    load_workbook = None


def build_portfolio_context(p, include_details=True):
    """Return context data for a portfolio."""
    positions = []
    total_value = p.cash_balance
    if include_details:
        for symbol, qty in p.holdings.items():
            mid_local = currency = fx_rate = value_usd = None
            try:
                quote = get_quote(symbol)
                price_val = quote.get("price")
                currency = quote.get("currency")
                fx_rate_val = quote.get("fx_rate")
                if price_val is not None and fx_rate_val is not None:
                    mid_local = Decimal(str(price_val))
                    fx_rate = Decimal(str(fx_rate_val))
                    value_usd = mid_local * fx_rate * Decimal(str(qty))
            except Exception:
                pass
            positions.append({
                "symbol": symbol,
                "quantity": qty,
                "mid_local": mid_local,
                "currency": currency,
                "fx_rate": fx_rate,
                "value_usd": value_usd,
            })
            if value_usd is not None:
                total_value += value_usd

    orders_data = []
    if include_details:
        for o in p.orders.all().order_by("-executed_at"):
            total_usd = o.price_executed * o.fx_rate * o.quantity
            orders_data.append({
                "executed_at": o.executed_at,
                "symbol": o.symbol,
                "side": o.side,
                "quantity": o.quantity,
                "price_local": o.price_executed,
                "currency": o.currency,
                "fx_rate": o.fx_rate,
                "total_value_usd": total_usd,
            })

    history_data = []
    for snap in p.snapshots.all().order_by("timestamp"):
        history_data.append({
            "date": snap.timestamp.date().isoformat(),
            "value": snap.total_value,
        })
    if not history_data:
        history_data.append({
            "date": timezone.now().date().isoformat(),
            "value": total_value,
        })

    benchmark_data = []
    snaps = list(p.snapshots.all().order_by("timestamp"))
    if snaps:
        per_ticker = {t: [] for t, _ in BENCHMARK_CHOICES}
        for snap in snaps:
            date_iso = snap.timestamp.date().isoformat()
            for ticker, _ in BENCHMARK_CHOICES:
                price = snap.benchmark_values.get(ticker)
                if price is not None:
                    per_ticker[ticker].append({"date": date_iso, "price_usd": price})
        for ticker, name in BENCHMARK_CHOICES:
            pts = per_ticker[ticker]
            if pts:
                base = pts[0]["price_usd"]
                for pt in pts:
                    pt["price_usd"] = (pt["price_usd"] / base) * 100_000
            benchmark_data.append({
                "ticker": ticker,
                "label": name,
                "data": pts,
            })
    else:
        for ticker, name in BENCHMARK_CHOICES:
            benchmark_data.append({
                "ticker": ticker,
                "label": name,
                "data": [],
            })

    return {
        "positions": positions if include_details else [],
        "total_value": total_value,
        "orders_data": orders_data if include_details else [],
        "history_data": history_data,
        "history_data_json": json.dumps(history_data, cls=DjangoJSONEncoder),
        "benchmark_data": benchmark_data,
        "benchmark_data_json": json.dumps(benchmark_data, cls=DjangoJSONEncoder),
        "default_benchmarks": p.benchmarks,
    }


class PortfolioCreateView(LoginRequiredMixin, CreateView):
    model = Portfolio
    form_class = PortfolioForm
    template_name = "portfolios/portfolio_form.html"
    success_url = reverse_lazy("portfolios:portfolio-detail")

    def dispatch(self, request, *args, **kwargs):
        if Portfolio.objects.filter(user=request.user).exists():
            return redirect("portfolios:portfolio-detail")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class PortfolioDetailView(LoginRequiredMixin, DetailView):
    model = Portfolio
    template_name = "portfolios/portfolio_detail.html"
    context_object_name = "portfolio"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not Portfolio.objects.filter(user=request.user).exists():
            return render(request, "portfolios/portfolio_empty.html")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return get_object_or_404(Portfolio, user=self.request.user)

    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(build_portfolio_context(self.object))
        ctx["is_owner"] = True
        ctx["private_view"] = False
        ctx["allowed_count"] = self.object.allowed_emails.count()
        ctx["order_form"] = OrderForm()
        return ctx


class PublicPortfolioDetailView(DetailView):
    model = Portfolio
    template_name = "portfolios/portfolio_detail.html"
    context_object_name = "portfolio"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        is_owner = (
            self.request.user.is_authenticated and self.request.user == self.object.user
        )
        is_allowed = False
        if (
            self.object.is_private
            and self.request.user.is_authenticated
            and self.request.user != self.object.user
        ):
            identifier = self.request.user.email or self.request.user.username
            is_allowed = self.object.allowed_emails.filter(
                email=identifier
            ).exists()
        include_details = is_owner or not self.object.is_private or is_allowed
        ctx.update(build_portfolio_context(self.object, include_details=include_details))
        ctx["is_owner"] = is_owner
        ctx["is_allowed"] = is_allowed
        ctx["private_view"] = self.object.is_private and not include_details
        if self.request.user.is_authenticated:
            ctx["is_following"] = self.object.followers.filter(
                follower=self.request.user
            ).exists()
        else:
            ctx["is_following"] = False
        ctx["allowed_count"] = self.object.allowed_emails.count()
        return ctx


@require_POST
@login_required
def toggle_privacy(request):
    """Toggle the current user's portfolio privacy flag."""
    portfolio = get_object_or_404(Portfolio, user=request.user)
    portfolio.is_private = not portfolio.is_private
    portfolio.save()
    return redirect("portfolios:portfolio-detail")


@require_POST
@login_required
def change_display_name(request):
    """Update the portfolio's display name for the current user."""
    portfolio = get_object_or_404(Portfolio, user=request.user)
    new_name = request.POST.get("name", "").strip()
    if new_name:
        portfolio.name = new_name
        portfolio.save()
    return redirect("portfolios:portfolio-detail")


@require_POST
@login_required
def toggle_follow(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk)
    if portfolio.user == request.user:
        return redirect("portfolios:portfolio-public-detail", pk=pk)
    identifier = request.user.email or request.user.username
    allowed = (
        not portfolio.is_private
        or portfolio.allowed_emails.filter(email=identifier).exists()
    )
    if not allowed:
        return redirect("portfolios:portfolio-public-detail", pk=pk)
    rel, created = PortfolioFollower.objects.get_or_create(
        portfolio=portfolio, follower=request.user
    )
    if not created:
        rel.delete()
    return redirect("portfolios:portfolio-public-detail", pk=pk)


@login_required
def allow_list(request):
    portfolio = get_object_or_404(Portfolio, user=request.user, is_private=True)
    emails = portfolio.allowed_emails.all().order_by("email")
    email_form = AllowedEmailForm()
    upload_form = AllowedEmailUploadForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_email":
            email_form = AllowedEmailForm(request.POST)
            if email_form.is_valid():
                PortfolioAllowedEmail.objects.get_or_create(
                    portfolio=portfolio, email=email_form.cleaned_data["email"]
                )
                return redirect("portfolios:portfolio-allow-list")
        elif action == "upload":
            upload_form = AllowedEmailUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                file = upload_form.cleaned_data["file"]
                try:
                    emails_raw = []
                    if file.name.lower().endswith(".csv"):
                        file.seek(0)
                        data = file.read().decode("utf-8")
                        reader = csv.reader(StringIO(data))
                        emails_raw = [row[0] for row in reader if row]
                    else:
                        if load_workbook is None:
                            raise ImportError("openpyxl is required for Excel uploads")
                        file.seek(0)
                        wb = load_workbook(file)
                        ws = wb.active
                        emails_raw = [
                            row[0]
                            for row in ws.iter_rows(min_col=1, max_col=1, values_only=True)
                            if row
                        ]
                    for e in emails_raw:
                        if not e:
                            continue
                        email = str(e).strip().lstrip("\ufeff")
                        try:
                            validate_email(email)
                        except ValidationError:
                            continue
                        PortfolioAllowedEmail.objects.get_or_create(
                            portfolio=portfolio, email=email
                        )
                except Exception:
                    pass
                return redirect("portfolios:portfolio-allow-list")
        elif action == "delete":
            email_id = request.POST.get("id")
            PortfolioAllowedEmail.objects.filter(
                id=email_id, portfolio=portfolio
            ).delete()
            return redirect("portfolios:portfolio-allow-list")
        elif action == "delete_all":
            portfolio.allowed_emails.all().delete()
            return redirect("portfolios:portfolio-allow-list")
    return render(
        request,
        "portfolios/allow_list.html",
        {
            "portfolio": portfolio,
            "emails": emails,
            "email_form": email_form,
            "upload_form": upload_form,
        },
    )


class PortfolioExploreView(ListView):
    model = Portfolio
    template_name = "portfolios/portfolio_explore.html"
    context_object_name = "portfolios"

    def get_queryset(self):
        qs = Portfolio.objects.all()
        query = self.request.GET.get("q")
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(substack_url__icontains=query))
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for p in ctx["portfolios"]:
            snap = p.snapshots.order_by("-timestamp").first()
            if snap:
                p.total_value_cached = snap.total_value
            else:
                p.total_value_cached = p.cash_balance
        ctx["search_query"] = self.request.GET.get("q", "")
        return ctx


class FollowedPortfoliosView(LoginRequiredMixin, ListView):
    model = Portfolio
    template_name = "portfolios/portfolio_followed.html"
    context_object_name = "portfolios"

    def get_queryset(self):
        return (
            Portfolio.objects.filter(followers__follower=self.request.user)
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for p in ctx["portfolios"]:
            snap = p.snapshots.order_by("-timestamp").first()
            if snap:
                p.total_value_cached = snap.total_value
            else:
                p.total_value_cached = p.cash_balance
        return ctx


class OrderCreateView(LoginRequiredMixin, CreateView):
    model = Order
    form_class = OrderForm
    template_name = "portfolios/portfolio_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.portfolio = get_object_or_404(Portfolio, user=request.user)
        if request.method.lower() == "get":
            return redirect("portfolios:portfolio-detail")
        return super().dispatch(request, *args, **kwargs)


    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["portfolio"] = self.portfolio
        ctx.update(build_portfolio_context(self.portfolio))
        ctx["is_owner"] = True
        ctx["private_view"] = False
        ctx["allowed_count"] = self.portfolio.allowed_emails.count()
        ctx["order_form"] = kwargs.get("form", OrderForm())
        return ctx

    #-------------

    def form_valid(self, form):
        print("Running form_valid")
        form.instance.portfolio = self.portfolio

        symbol = form.cleaned_data["symbol"].upper()
        side = form.cleaned_data["side"]  # "BUY" or "SELL"
        quantity = form.cleaned_data["quantity"]

        print(symbol, side, quantity)

        # 1) Fetch price
        try:
            quote = get_quote(symbol)
            price = Decimal(str(quote["price"]))
            bid = Decimal(str(quote["bid"])) if quote.get("bid") is not None else None
            ask = Decimal(str(quote["ask"])) if quote.get("ask") is not None else None
            traded_today = quote["traded_today"]
            currency = quote["currency"]
            fx_rate = Decimal(str(quote["fx_rate"]))
            market_state = quote["market_state"]
            print(price, bid, ask, traded_today, currency, fx_rate)
        except Exception:
            form.add_error(None, f"Could not fetch live quote for “{symbol}”.")
            return self.form_invalid(form)

        # if market_state != "REGULAR":
        #     form.add_error(
        #         None,
        #         "Order failed because the market is currently closed."
        #     )
        #     return self.form_invalid(form)

        # 2) Compute execution_price & validate
        if side == "BUY":
            execution_price = price if traded_today else ask
            total_cost = execution_price * fx_rate * quantity
            if self.portfolio.cash_balance < total_cost:
                form.add_error(
                    None,
                    f"Insufficient cash: need ${total_cost:.2f}, have ${self.portfolio.cash_balance:.2f}."
                )
                return self.form_invalid(form)

        else:  # SELL
            execution_price = price if traded_today else bid
            held_qty = self.portfolio.holdings.get(symbol, 0)
            if held_qty < quantity:
                form.add_error(
                    None,
                    f"Cannot sell {quantity} shares of {symbol}; you only hold {held_qty}."
                )
                return self.form_invalid(form)

        # 3) Assign price and save Order
        form.instance.price_executed = execution_price
        form.instance.fx_rate = fx_rate
        form.instance.currency = currency
        response = super().form_valid(form)

        # 4) Update cash_balance and holdings
        if side == "BUY":
            self.portfolio.cash_balance -= execution_price * fx_rate * quantity
            new_qty = float(self.portfolio.holdings.get(symbol, 0)) + quantity
            self.portfolio.holdings[symbol] = new_qty
        else:  # SELL
            self.portfolio.cash_balance += execution_price * fx_rate * quantity
            remaining = float(self.portfolio.holdings.get(symbol, 0)) - quantity
            if remaining == 0:
                # remove key if zero
                self.portfolio.holdings.pop(symbol, None)
            else:
                self.portfolio.holdings[symbol] = remaining

        self.portfolio.save()
        follower_emails = list(
            self.portfolio.followers.values_list("follower__email", flat=True)
        )
        if follower_emails:
            send_mail(
                f"New trade in {self.portfolio.name}",
                f"{self.portfolio.user.username} executed {side} {quantity} {symbol} at {execution_price} {currency}",
                None,
                follower_emails,
                fail_silently=True,
            )
        return response



    def form_invalid(self, form):
        """
        If validation fails above, form.add_error(…) was called.
        Returning form_invalid(form) will re-render the page with errors.
        """
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("portfolios:portfolio-detail")


@login_required
def portfolio_history(request):
    p = Portfolio.objects.filter(user=request.user).first()
    if not p:
        return JsonResponse({"error": "Not found"}, status=404)

    data = [
        {
            "timestamp": snap.timestamp.isoformat(),
            "value": snap.total_value,
        }
        for snap in p.snapshots.all()
    ]

    # Create single datapoint if no snapshots
    if not data:
        total_value = p.cash_balance
        for symbol, qty in p.holdings.items():
            try:
                quote = get_quote(symbol)
                total_value += Decimal(str(quote["price"])) * Decimal(str(quote["fx_rate"])) * Decimal(str(qty))
            except Exception:
                pass
        data.append({
            "timestamp": timezone.now().isoformat(),
            "value": total_value,
        })


    return JsonResponse(data, safe=False)


@login_required
def account_details(request):
    portfolio = Portfolio.objects.filter(user=request.user).first()
    return render(
        request,
        "portfolios/account_details.html",
        {"portfolio": portfolio},
    )
