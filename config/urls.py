from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from drf_spectacular.utils import extend_schema
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


class TaggedSpectacularAPIView(SpectacularAPIView):
    """Rol: Tizimga kirgan foydalanuvchi / Dasturchi — OpenAPI sxemasi."""

    @extend_schema(
        tags=["Schema"],
        summary="API OpenAPI sxemasi [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Tizimdagi barcha API "
            "endpointlarning OpenAPI/JSON sxemasini (so'rov, javob va "
            "parametrlarga oid hujjat spetsifikatsiyasini) qaytaradi."
        ),
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("hub.urls")),
    path("api/schema/", TaggedSpectacularAPIView.as_view(), name="schema"),
    path("", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)