from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import sections, views

router = DefaultRouter()
# --- sections.py (kengaytirilgan bo'limlar) ---
router.register("attendance", sections.AttendanceViewSet, basename="attendance")
router.register("schedule", sections.ScheduleViewSet, basename="schedule")
router.register("notifications", sections.NotificationViewSet, basename="notifications")
# --- views.py ---
router.register("grades", views.GradeViewSet, basename="grades")
router.register("assignments", views.AssignmentViewSet, basename="assignments")
router.register("announcements", views.AnnouncementViewSet, basename="announcements")
router.register("library", views.BookViewSet, basename="library")
router.register("chat", views.ChatViewSet, basename="chat")
router.register("goals", views.GoalViewSet, basename="goals")

urlpatterns = [
    path("auth/login/", TokenObtainPairView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("dashboard/", views.DashboardView.as_view()),
    path("search/", views.SearchView.as_view()),
    # --- sections.py ---
    path("profile/", sections.ProfileView.as_view()),
    path("rating/", sections.RatingView.as_view()),
    path("settings/", sections.SettingsView.as_view()),
    path("settings/change-password/", sections.ChangePasswordView.as_view()),
    path("", include(router.urls)),
]