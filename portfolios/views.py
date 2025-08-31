from datetime import timedelta
from django.shortcuts import redirect, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import DetailView, CreateView, FormView
from bisect import bisect_right
from django.utils import timezone

from core.yfinance_client import get_quote
from .models import Portfolio, Order, PortfolioSnapshot
from .constants import BENCHMARK_CHOICES
from .forms import PortfolioForm, OrderForm, PortfolioLookupForm
import yfinance as yf


def build_portfolio_context(p, include_details=True):
    """Return context data for a portfolio."""
    positions = []
    total_value = p.cash_balance
    if include_details:
        for symbol, qty in p.holdings.items():
            mid_local = currency = fx_rate = value_usd = None
            try:
                quote = get_quote(symbol)
                price = quote["price"]
                traded_today = quote["traded_today"]
                currency = quote["currency"]
                fx_rate = quote["fx_rate"]
                mid_local = price
                value_usd = mid_local * fx_rate * qty
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
    if p.benchmarks and snaps:
        snap_dates = [snap.timestamp.date() for snap in snaps]
        first_date = snap_dates[0]
        last_date = snap_dates[-1]
        for ticker in p.benchmarks:
            label = next((name for sym, name in BENCHMARK_CHOICES if sym == ticker), ticker)
            try:
                yf_tkr = yf.Ticker(ticker)
                hist = yf_tkr.history(
                    start=(first_date - timedelta(days=30)).isoformat(),
                    end=(last_date + timedelta(days=1)).isoformat(),
                    interval="1d",
                )
            except Exception:
                hist = None

            daily_points = []
            if hist is not None and not hist.empty:
                hist = hist.sort_index()
                closes = hist["Close"]
                indexed_dates = [idx.date() for idx in closes.index]
                close_values = [float(v) for v in closes.values]
                for date in snap_dates:
                    pos = bisect_right(indexed_dates, date) - 1
                    if pos < 0:
                        continue
                    last_close = close_values[pos]
                    ccy = yf_tkr.fast_info.get("currency", "USD")
                    if ccy != "USD":
                        fx_tkr = yf.Ticker(f"{ccy}USD=X")
                        fx_rate = 1.0
                        try:
                            fx_hist = fx_tkr.history(
                                start=date.isoformat(),
                                end=(date + timedelta(days=1)).isoformat(),
                                interval="1d",
                            )
                            if not fx_hist.empty:
                                fx_rate = float(fx_hist["Close"].iloc[0])
                            else:
                                fx_hist2 = fx_tkr.history(
                                    start=(date - timedelta(days=7)).isoformat(),
                                    end=(date + timedelta(days=1)).isoformat(),
                                    interval="1d",
                                )
                                fx_hist2 = fx_hist2[fx_hist2.index.date <= date]
                                if not fx_hist2.empty:
                                    fx_rate = float(fx_hist2["Close"].iloc[-1])
                        except Exception:
                            fx_rate = 1.0
                    else:
                        fx_rate = 1.0
                    price_usd = last_close * fx_rate
                    daily_points.append({"date": date.isoformat(), "price_usd": price_usd})

            if daily_points:
                base_price = daily_points[0]["price_usd"]
                for pt in daily_points:
                    pt["price_usd"] = (pt["price_usd"] / base_price) * 100_000

            benchmark_data.append({
                "ticker": ticker,
                "label": label,
                "data": daily_points,
            })

    return {
        "positions": positions if include_details else [],
        "total_value": total_value,
        "orders_data": orders_data if include_details else [],
        "history_data": history_data,
        "benchmark_data": benchmark_data,
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

    def get_object(self, queryset=None):
        return get_object_or_404(Portfolio, user=self.request.user)

    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(build_portfolio_context(self.object))
        ctx["is_owner"] = True
        ctx["private_view"] = False
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
        include_details = is_owner or not self.object.is_private
        ctx.update(build_portfolio_context(self.object, include_details=include_details))
        ctx["is_owner"] = is_owner
        ctx["private_view"] = self.object.is_private and not is_owner
        return ctx


class PortfolioLookupView(FormView):
    form_class = PortfolioLookupForm
    template_name = "portfolios/portfolio_lookup.html"

    def form_valid(self, form):
        url = form.cleaned_data["substack_url"]
        portfolio = Portfolio.objects.filter(substack_url=url).first()
        if not portfolio:
            form.add_error("substack_url", "No portfolio found for that Substack URL.")
            return self.form_invalid(form)
        return redirect("portfolios:portfolio-public-detail", pk=portfolio.pk)


class OrderCreateView(LoginRequiredMixin, CreateView):
    model = Order
    form_class = OrderForm
    template_name = "portfolios/order_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.portfolio = get_object_or_404(Portfolio, user=request.user)
        return super().dispatch(request, *args, **kwargs)

    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["portfolio"] = self.portfolio
        return ctx

    #-------------

    def form_valid(self, form):
        form.instance.portfolio = self.portfolio

        symbol = form.cleaned_data["symbol"].upper()
        side = form.cleaned_data["side"]  # "BUY" or "SELL"
        quantity = form.cleaned_data["quantity"]

        # 1) Fetch price
        try:
            quote = get_quote(symbol)
            price = quote["price"]
            bid = quote["bid"]
            ask = quote["ask"]
            traded_today = quote["traded_today"]
            currency = quote["currency"]
            fx_rate = quote["fx_rate"]
            market_state = quote["market_state"]
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
            total_cost = execution_price * quantity * fx_rate
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
            self.portfolio.cash_balance -= execution_price * quantity * fx_rate
            new_qty = float(self.portfolio.holdings.get(symbol, 0)) + quantity
            self.portfolio.holdings[symbol] = new_qty
        else:  # SELL
            self.portfolio.cash_balance += execution_price * quantity * fx_rate
            remaining = float(self.portfolio.holdings.get(symbol, 0)) - quantity
            if remaining == 0:
                # remove key if zero
                self.portfolio.holdings.pop(symbol, None)
            else:
                self.portfolio.holdings[symbol] = remaining

        self.portfolio.save()
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
                total_value += quote["price"] * quote["fx_rate"] * qty
            except Exception:
                pass
        data.append({
            "timestamp": timezone.now().isoformat(),
            "value": total_value,
        })


    return JsonResponse(data, safe=False)
