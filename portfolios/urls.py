from django.urls import path
from . import views

app_name = "portfolios"

urlpatterns = [
    path("", views.PortfolioDetailView.as_view(), name="portfolio-detail"),
    path("explore/", views.PortfolioExploreView.as_view(), name="portfolio-explore"),
    path("followed/", views.FollowedPortfoliosView.as_view(), name="followed-portfolios"),
    path("account/", views.account_details, name="account-details"),
    path("account/verify-email/", views.verify_email_change, name="account-verify-email"),
    path("public/<int:pk>/", views.PublicPortfolioDetailView.as_view(), name="portfolio-public-detail"),
    path("create/", views.PortfolioCreateView.as_view(), name="portfolio-create"),
    path("order/", views.OrderCreateView.as_view(), name="order-create"),
    path("quote/", views.lookup_quote, name="quote-lookup"),
    path("toggle-privacy/", views.toggle_privacy, name="portfolio-toggle-privacy"),
    path("follow/<int:pk>/", views.toggle_follow, name="portfolio-follow-toggle"),
    path("allow-list/", views.allow_list, name="portfolio-allow-list"),
    path("history/", views.portfolio_history, name="portfolio-history"),
]
