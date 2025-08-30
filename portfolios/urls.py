from django.urls import path
from . import views

app_name = "portfolios"

urlpatterns = [
    path("", views.PortfolioDetailView.as_view(), name="portfolio-detail"),
    path("create/", views.PortfolioCreateView.as_view(), name="portfolio-create"),
    path("order/", views.OrderCreateView.as_view(), name="order-create"),
    path("history/", views.portfolio_history, name="portfolio-history"),
]
