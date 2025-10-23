from django.contrib import admin

from .models import (
    Announcement,
    AnnouncementNotification,
    AnnouncementType,
    Company,
    CompanyAnnouncementPreference,
    EmailThrottle,
    UserAnnouncementTypePreference,
    Watchlist,
    WatchlistCompany,
)


@admin.register(AnnouncementType)
class AnnouncementTypeAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "default_is_important")
    search_fields = ("label", "code")
    list_filter = ("default_is_important",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "ticker", "isin")
    search_fields = ("name", "ticker", "isin")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "announcement_type", "published_at")
    list_filter = ("announcement_type", "company")
    search_fields = ("title", "company__name", "company__ticker")
    autocomplete_fields = ("company", "announcement_type")


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "created_at")
    search_fields = ("name", "user__username", "user__email")
    autocomplete_fields = ("user",)


@admin.register(WatchlistCompany)
class WatchlistCompanyAdmin(admin.ModelAdmin):
    list_display = ("watchlist", "company")
    autocomplete_fields = ("watchlist", "company")


@admin.register(UserAnnouncementTypePreference)
class UserAnnouncementTypePreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "announcement_type", "is_important")
    list_filter = ("announcement_type", "is_important")
    autocomplete_fields = ("user", "announcement_type")


@admin.register(CompanyAnnouncementPreference)
class CompanyAnnouncementPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "announcement_type", "is_important")
    list_filter = ("announcement_type", "is_important")
    autocomplete_fields = ("user", "company", "announcement_type")


@admin.register(AnnouncementNotification)
class AnnouncementNotificationAdmin(admin.ModelAdmin):
    list_display = ("announcement", "user", "sent_at", "delivered")
    list_filter = ("delivered",)
    autocomplete_fields = ("announcement", "user")


@admin.register(EmailThrottle)
class EmailThrottleAdmin(admin.ModelAdmin):
    list_display = ("user", "window_start", "emails_sent")
    autocomplete_fields = ("user",)
