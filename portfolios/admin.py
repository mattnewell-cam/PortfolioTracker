from django.contrib import admin
from .models import Portfolio, Order

@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "name", "cash_balance", "created_at")
    list_filter = ("user",)
    search_fields = ("name", "user__username")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "portfolio", "symbol", "side", "quantity", "price_executed", "executed_at")
    list_filter = ("symbol", "side")
    search_fields = ("portfolio__name", "symbol")
