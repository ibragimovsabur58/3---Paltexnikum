from django.urls import include, path
from drf_spectacular.utils import extend_schema
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import sections, views


# ==============================================================================
# AUTENTIFIKATSIYA VIEWLARI (Swagger uchun Rol va Description bilan)
# ==============================================================================

class TaggedTokenObtainPairView(TokenObtainPairView):
    @extend_schema(
        tags=["Autentifikatsiya"],
        summary="Tizimga kirish (Login) [Rol: Mehmon]",
        description=(
            "Rol: Mehmon (tizimga kirmagan foydalanuvchi). Login (username/email) "
            "va parolni yuborib tizimga kirish hamda JWT access va refresh "
            "tokenlarni olish uchun endpoint."
        ),
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class TaggedTokenRefreshView(TokenRefreshView):
    @extend_schema(
        tags=["Autentifikatsiya"],
        summary="Tokenni yangilash (Refresh) [Rol: Refresh token egasi]",
        description=(
            "Rol: Refresh token egasi. Amal qilish muddati tugagan access "
            "tokenni qayta login qilmasdan yangilash uchun refresh tokenni "
            "qabul qiladi va yangi access token qaytaradi."
        ),
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


# ==============================================================================
# ROUTER VA URL YO'LLARI
# ==============================================================================

router = DefaultRouter()

# --- 1. sections.py (Profil, Davomat, Dars jadvali, Bildirishnomalar) ---
router.register("attendance", sections.AttendanceViewSet, basename="attendance")
router.register("schedule", sections.ScheduleViewSet, basename="schedule")
router.register("notifications", sections.NotificationViewSet, basename="notifications")

# --- 2. views.py (Baholar, Topshiriqlar, E'lonlar, Kutubxona, Chat, Maqsadlar) ---
router.register("grades", views.GradeViewSet, basename="grades")
router.register("assignments", views.AssignmentViewSet, basename="assignments")
router.register("announcements", views.AnnouncementViewSet, basename="announcements")
router.register("library", views.BookViewSet, basename="library")
router.register("chat", views.ChatViewSet, basename="chat")
router.register("goals", views.GoalViewSet, basename="goals")


urlpatterns = [
    # --- Autentifikatsiya [Rol: Mehmon / Refresh token egasi] ---
    path("auth/login/", TaggedTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TaggedTokenRefreshView.as_view(), name="token_refresh"),

    # --- Asosiy sahifa va Qidiruv (views.py) [Rol: Talaba] ---
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("search/", views.SearchView.as_view(), name="search"),

    # --- Profil va Reyting (sections.py) [Rol: Talaba] ---
    path("profile/", sections.ProfileView.as_view(), name="profile"),
    path("rating/", sections.RatingView.as_view(), name="rating"),

    # --- Sozlamalar (sections.py) [Rol: Tizimga kirgan foydalanuvchi] ---
    path("settings/", sections.SettingsView.as_view(), name="settings"),
    path("settings/change-password/", sections.ChangePasswordView.as_view(), name="change-password"),

    # --- Router orqali ulangan barcha ViewSet endpointlar ---
    path("", include(router.urls)),
]