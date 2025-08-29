from django.urls import path
from . import views

app_name = "portfolios"

urlpatterns = [
    path("", views.PortfolioListView.as_view(), name="portfolio-list"),
    path("create/", views.PortfolioCreateView.as_view(), name="portfolio-create"),
    path("<int:pk>/", views.PortfolioDetailView.as_view(), name="portfolio-detail"),
    path("<int:pk>/order/", views.OrderCreateView.as_view(), name="order-create"),
    path("<int:pk>/history/", views.portfolio_history, name="portfolio-history"),

]
