from django.urls import path
from . import views

app_name = "portfolios"

urlpatterns = [
    path("", views.PortfolioDetailView.as_view(), name="portfolio-detail"),
    path("lookup/", views.PortfolioLookupView.as_view(), name="portfolio-lookup"),
    path("explore/", views.PortfolioExploreView.as_view(), name="portfolio-explore"),
    path("public/<int:pk>/", views.PublicPortfolioDetailView.as_view(), name="portfolio-public-detail"),
    path("create/", views.PortfolioCreateView.as_view(), name="portfolio-create"),
    path("order/", views.OrderCreateView.as_view(), name="order-create"),
    path("toggle-privacy/", views.toggle_privacy, name="portfolio-toggle-privacy"),
    path("history/", views.portfolio_history, name="portfolio-history"),
]
