"""
Chap menyudagi bo'limlar: Profilim, Davomat, Dars jadvali, Reyting,
Bildirishnomalar, Sozlamalar.
"""
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.db.models import Avg, Count, Q
from django.utils import timezone

from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, extend_schema_view

from .models import (
    Attendance, Grade, Lesson, Notification, Student,
    Subject, Submission, UserSettings,
)

WEEKDAYS = {
    1: "Dushanba",
    2: "Seshanba",
    3: "Chorshanba",
    4: "Payshanba",
    5: "Juma",
    6: "Shanba",
    7: "Yakshanba",
}


# ==============================================================================
# RUXSATLAR (PERMISSIONS) VA YORDAMCHI FUNKSIYALAR
# ==============================================================================

class HasStudentProfile(permissions.IsAuthenticated):
    """Rol: Talaba — faqat tizimga kirgan va Student profiliga ega foydalanuvchilar."""
    def has_permission(self, request, view):
        return super().has_permission(request, view) and hasattr(request.user, "student")


def parse_month(value):
    """'2026-11' -> (2026, 11). Yuborilmasa joriy oy, noto'g'ri bo'lsa 400."""
    today = timezone.localdate()
    if not value:
        return today.year, today.month
    try:
        y, m = value.split("-")
        y, m = int(y), int(m)
        if 1 <= m <= 12:
            return y, m
    except ValueError:
        pass
    raise ValidationError({"month": "Format YYYY-MM bo'lishi kerak, masalan 2026-11."})


def _summary(qs):
    """Berilgan davomat queryset bo'yicha foiz va holatlar sonini hisoblaydi."""
    c = qs.aggregate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
        total=Count("id"),
    )
    percent = round(c["present"] / c["total"] * 100) if c["total"] else 0
    return {
        "percent": percent,
        "keldi": c["present"],
        "qoldirilgan": c["absent"],
        "kechikish": c["late"],
        "jami": c["total"],
    }


# ==============================================================================
# SERIALIZERLAR
# ==============================================================================

class ProfileSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", required=False, allow_blank=True)
    group = serializers.CharField(source="group.name", read_only=True)
    direction = serializers.CharField(source="group.direction", read_only=True)

    class Meta:
        model = Student
        fields = [
            "id", "username", "first_name", "last_name", "email", "phone",
            "birth_date", "address", "bio", "avatar",
            "student_id", "group", "direction", "course",
        ]
        read_only_fields = ["student_id", "course"]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save()
        return super().update(instance, validated_data)


class AttendanceItemSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="subject.name")
    status_display = serializers.CharField(source="get_status_display")

    class Meta:
        model = Attendance
        fields = ["id", "subject", "date", "status", "status_display"]


class LessonSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="subject.name")
    teacher = serializers.CharField(source="subject.teacher")
    weekday_name = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            "id", "subject", "teacher", "weekday", "weekday_name",
            "start_time", "end_time", "room",
        ]

    def get_weekday_name(self, obj):
        return WEEKDAYS.get(obj.weekday)


class NotificationSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "category", "category_display", "title", "text", "is_read", "created_at"]
        read_only_fields = ["category", "title", "text", "created_at"]


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = [
            "language", "dark_mode", "notifications_enabled",
            "email_notifications", "deadline_reminders", "grade_notifications",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Joriy parol noto'g'ri.")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value


# ==============================================================================
# 1-BO'LIM: TALABA API'LARI (Rol: Talaba -> HasStudentProfile)
# ==============================================================================

# ----------------------------------------------------------
# 1.1 PROFILIM | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    get=extend_schema(
        tags=["Profilim"],
        summary="Profil va statistika ma'lumotlari [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning shaxsiy profil ma'lumotlarini "
            "(ism-familiya, username, email, telefon, tug'ilgan sana, manzil, "
            "bio, avatar, talaba ID, guruh, yo'nalish, kurs) hamda 5 ta "
            "ko'rsatkichni (davomat foizi, o'rtacha baho, fanlar soni, "
            "topshirilgan vazifalar va bajarilgan maqsadlar soni) qaytaradi."
        ),
    ),
    patch=extend_schema(
        tags=["Profilim"],
        summary="Profilni tahrirlash [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaga o'z profilidagi ruxsat etilgan "
            "ma'lumotlarni (shu jumladan multipart orqali avatar rasmini) "
            "qisman o'zgartirish imkonini beradi."
        ),
    ),
)
class ProfileView(APIView):
    """GET /api/profile/ — profil + statistika | PATCH /api/profile/ — tahrirlash"""
    permission_classes = [HasStudentProfile]

    def _stats(self, student):
        att = Attendance.objects.filter(student=student).aggregate(
            total=Count("id"),
            present=Count("id", filter=Q(status="present")),
        )
        avg = Grade.objects.filter(student=student).aggregate(a=Avg("score"))["a"] or 0
        return {
            "attendance_percent": round(att["present"] / att["total"] * 100) if att["total"] else 0,
            "average_grade": round(avg, 2),
            "subjects_count": Subject.objects.filter(groups=student.group).count(),
            "submitted_assignments": Submission.objects.filter(student=student).count(),
            "goals_done": student.goals.filter(is_done=True).count(),
        }

    def get(self, request):
        student = request.user.student
        data = ProfileSerializer(student, context={"request": request}).data
        return Response({"profile": data, "stats": self._stats(student)})

    def patch(self, request):
        if not request.data:
            return Response(
                {"detail": "Yuborilgan ma'lumot bo'sh."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        student = request.user.student
        s = ProfileSerializer(student, data=request.data, partial=True, context={"request": request})
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


# ----------------------------------------------------------
# 1.2 DAVOMAT | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Davomat"],
        summary="Davomat yozuvlari ro'yxati [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning davomat yozuvlari ro'yxatini qaytaradi. "
            "?month=2026-11, ?status=present|absent|late va ?subject=<id> "
            "parametrlari orqali filtrlash mumkin."
        ),
    ),
)
class AttendanceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/attendance/?month=2026-11&status=absent&subject=3"""
    serializer_class = AttendanceItemSerializer
    permission_classes = [HasStudentProfile]

    def _base(self):
        return Attendance.objects.filter(student=self.request.user.student).select_related("subject")

    def get_queryset(self):
        qs, p = self._base(), self.request.query_params
        if p.get("month"):
            y, m = parse_month(p["month"])
            qs = qs.filter(date__year=y, date__month=m)
        if p.get("status") in ("present", "absent", "late"):
            qs = qs.filter(status=p["status"])
        if p.get("subject"):
            qs = qs.filter(subject_id=p["subject"])
        return qs

    @extend_schema(
        tags=["Davomat"],
        summary="Davomat umumiy statistikasi [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning davomat foizi (percent), keldi, "
            "qoldirilgan, kechikish va jami darslar sonini qaytaradi. "
            "Ixtiyoriy ?month=2026-11 parametri bilan oy bo'yicha hisoblaydi."
        ),
    )
    @action(detail=False)
    def summary(self, request):
        qs = self._base()
        if request.query_params.get("month"):
            y, m = parse_month(request.query_params["month"])
            qs = qs.filter(date__year=y, date__month=m)
        return Response(_summary(qs))

    @extend_schema(
        tags=["Davomat"],
        summary="Davomat fanlar kesimida [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talaba guruhidagi har bir fan bo'yicha davomat "
            "statistikasini alohida hisoblab qaytaradi."
        ),
    )
    @action(detail=False, url_path="by-subject")
    def by_subject(self, request):
        subjects = Subject.objects.filter(groups=request.user.student.group)
        result = []
        for sub in subjects:
            row = _summary(self._base().filter(subject=sub))
            row.update(subject_id=sub.id, subject=sub.name)
            result.append(row)
        return Response(result)

    @extend_schema(
        tags=["Davomat"],
        summary="Davomat kalendari [Rol: Talaba]",
        description=(
            "Rol: Talaba. Tanlangan oy (?month=2026-11, yuborilmasa joriy oy) "
            "bo'yicha har bir kunning umumiy davomat holatini (absent, late, "
            "present) va yozuvlar sonini kalendar ko'rinishida qaytaradi."
        ),
    )
    @action(detail=False)
    def calendar(self, request):
        y, m = parse_month(request.query_params.get("month"))
        days = {}
        for a in self._base().filter(date__year=y, date__month=m):
            days.setdefault(a.date.isoformat(), []).append(a.status)
        out = []
        for d, statuses in sorted(days.items()):
            day_status = "absent" if "absent" in statuses else "late" if "late" in statuses else "present"
            out.append({"date": d, "status": day_status, "records": len(statuses)})
        return Response({"year": y, "month": m, "days": out})


# ----------------------------------------------------------
# 1.3 DARS JADVALI | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Dars jadvali"],
        summary="Dars jadvali ro'yxati [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talaba guruhining dars jadvali ro'yxatini qaytaradi. "
            "?weekday=1..7 parametri bilan hafta kuni bo'yicha filtrlash mumkin."
        ),
    ),
)
class ScheduleViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/schedule/ | /week/ | /today/ | /next/"""
    serializer_class = LessonSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        qs = Lesson.objects.filter(group=self.request.user.student.group).select_related("subject")
        if self.request.query_params.get("weekday"):
            qs = qs.filter(weekday=self.request.query_params["weekday"])
        return qs

    @extend_schema(
        tags=["Dars jadvali"],
        summary="Haftalik dars jadvali [Rol: Talaba]",
        description=(
            "Rol: Talaba. Dushanbadan Shanbagacha (1-6) bo'lgan haftalik dars "
            "jadvalini kunlar bo'yicha guruhlab va bugungi kunni (is_today) "
            "ko'rsatgan holda qaytaradi."
        ),
    )
    @action(detail=False)
    def week(self, request):
        today = timezone.localdate().isoweekday()
        grouped = {d: [] for d in range(1, 7)}
        for lesson in self.get_queryset():
            grouped.setdefault(lesson.weekday, []).append(self.get_serializer(lesson).data)
        return Response([
            {"weekday": d, "name": WEEKDAYS[d], "is_today": d == today, "lessons": items}
            for d, items in grouped.items()
        ])

    @extend_schema(
        tags=["Dars jadvali"],
        summary="Bugungi darslar [Rol: Talaba]",
        description="Rol: Talaba. Talabaning bugungi hafta kuni uchun belgilangan darslarini qaytaradi.",
    )
    @action(detail=False)
    def today(self, request):
        qs = self.get_queryset().filter(weekday=timezone.localdate().isoweekday())
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(
        tags=["Dars jadvali"],
        summary="Keyingi dars [Rol: Talaba]",
        description=(
            "Rol: Talaba. Hozirgi vaqtdan boshlab kelgusi 8 kun ichidagi eng "
            "birinchi bo'lib o'tadigan navbatdagi darsni (sanasi bilan birga) qaytaradi."
        ),
    )
    @action(detail=False)
    def next(self, request):
        now = timezone.localtime()
        base = Lesson.objects.filter(group=request.user.student.group).select_related("subject")
        for offset in range(0, 8):
            day = now + timedelta(days=offset)
            lessons = base.filter(weekday=day.isoweekday())
            if offset == 0:
                lessons = lessons.filter(start_time__gt=now.time())
            lesson = lessons.first()
            if lesson:
                data = self.get_serializer(lesson).data
                data["date"] = day.date().isoformat()
                return Response(data)
        return Response({"detail": "Dars topilmadi"}, status=status.HTTP_404_NOT_FOUND)


# ----------------------------------------------------------
# 1.4 REYTING | Rol: Talaba
# ----------------------------------------------------------
@extend_schema(
    tags=["Reyting"],
    summary="Talabalar reytingi [Rol: Talaba]",
    description=(
        "Rol: Talaba. Baholarga ega talabalarni o'rtacha bahosi bo'yicha "
        "reyting qiladi (teng ballarga bir xil o'rin beriladi). ?scope=group "
        "(faqat guruh), ?subject=<id> (bitta fan) va ?limit=20 (max 100) "
        "parametrlari mavjud. Foydalanuvchining o'z o'rni (my_rank) va o'rtacha "
        "bahosi (my_average) ham qaytariladi."
    ),
)
class RatingView(APIView):
    """GET /api/rating/?scope=group|all&subject=<id>&limit=20"""
    permission_classes = [HasStudentProfile]

    def get(self, request):
        me = request.user.student
        p = request.query_params
        scope = p.get("scope", "all")
        try:
            limit = min(int(p.get("limit", 20)), 100)
        except ValueError:
            raise ValidationError({"limit": "Butun son bo'lishi kerak."})

        flt = Q(grades__subject_id=p["subject"]) if p.get("subject") else None
        qs = Student.objects.select_related("user", "group")
        if scope == "group":
            qs = qs.filter(group=me.group)
        qs = (
            qs.annotate(
                avg=Avg("grades__score", filter=flt),
                grades_count=Count("grades", filter=flt),
            )
            .filter(grades_count__gt=0)
            .order_by("-avg", "-grades_count", "id")
        )

        rows, my_row, prev_avg, prev_rank, position = [], None, None, 0, 0
        for position, s in enumerate(qs, start=1):
            avg = round(s.avg, 2)
            rank = prev_rank if avg == prev_avg else position
            prev_avg, prev_rank = avg, rank
            row = {
                "rank": rank,
                "student_id": s.pk,
                "full_name": s.user.get_full_name(),
                "group": s.group.name,
                "average": avg,
                "grades_count": s.grades_count,
                "is_me": s.pk == me.pk,
            }
            if row["is_me"]:
                my_row = row
            if len(rows) < limit:
                rows.append(row)

        return Response({
            "scope": scope,
            "total": position if rows else 0,
            "my_rank": my_row["rank"] if my_row else None,
            "my_average": my_row["average"] if my_row else None,
            "top": rows,
        })


# ==============================================================================
# 2-BO'LIM: TIZIMGA KIRGAN FOYDALANUVCHI API'LARI (Rol: IsAuthenticated)
# ==============================================================================

# ----------------------------------------------------------
# 2.1 BILDIRISHNOMALAR | Rol: Tizimga kirgan foydalanuvchi
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Bildirishnomalar"],
        summary="Bildirishnomalar ro'yxati [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining o'z "
            "bildirishnomalarini qaytaradi. ?unread=1|true va ?category=... "
            "parametrlari bilan filtrlash mumkin."
        ),
    ),
    retrieve=extend_schema(
        tags=["Bildirishnomalar"],
        summary="Bitta bildirishnoma [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Tanlangan bitta "
            "bildirishnomaning batafsil ma'lumotlarini qaytaradi."
        ),
    ),
    partial_update=extend_schema(
        tags=["Bildirishnomalar"],
        summary="Bildirishnoma holatini yangilash [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Bildirishnomani o'qilgan yoki "
            "o'qilmagan holatga o'tkazadi (so'rovda is_read maydoni majburiy)."
        ),
    ),
    destroy=extend_schema(
        tags=["Bildirishnomalar"],
        summary="Bildirishnomani o'chirish [Rol: Tizimga kirgan foydalanuvchi]",
        description="Rol: Tizimga kirgan foydalanuvchi. Tanlangan bitta bildirishnomani o'chiradi.",
    ),
)
class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """GET /api/notifications/ | /unread-count/ | PATCH /<id>/ | POST /read-all/ | DELETE /<id>/ | /clear-read/"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "post", "delete", "head", "options"]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        p = self.request.query_params
        if p.get("unread") in ("1", "true"):
            qs = qs.filter(is_read=False)
        if p.get("category"):
            qs = qs.filter(category=p["category"])
        return qs

    def partial_update(self, request, *args, **kwargs):
        if "is_read" not in request.data:
            return Response(
                {"is_read": ["Bu maydon majburiy."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        tags=["Bildirishnomalar"],
        summary="O'qilmagan bildirishnomalar soni [Rol: Tizimga kirgan foydalanuvchi]",
        description="Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining o'qilmagan bildirishnomalari sonini qaytaradi.",
    )
    @action(detail=False, url_path="unread-count")
    def unread_count(self, request):
        n = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread": n})

    @extend_schema(
        tags=["Bildirishnomalar"],
        summary="Barchasini o'qilgan deb belgilash [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining barcha "
            "o'qilmagan bildirishnomalarini o'qilgan (is_read=True) qiladi va "
            "yangilanganlar sonini qaytaradi."
        ),
    )
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        n = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"updated": n})

    @extend_schema(
        tags=["Bildirishnomalar"],
        summary="O'qilgan bildirishnomalarni tozalash [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining barcha "
            "o'qilgan (is_read=True) bildirishnomalarini o'chiradi va "
            "o'chirilganlar sonini qaytaradi."
        ),
    )
    @action(detail=False, methods=["delete"], url_path="clear-read")
    def clear_read(self, request):
        n, _ = Notification.objects.filter(user=request.user, is_read=True).delete()
        return Response({"deleted": n})


# ----------------------------------------------------------
# 2.2 SOZLAMALAR | Rol: Tizimga kirgan foydalanuvchi
# ----------------------------------------------------------
@extend_schema_view(
    get=extend_schema(
        tags=["Sozlamalar"],
        summary="Sozlamalarni olish [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining til, "
            "qorong'i rejim va bildirishnoma sozlamalarini qaytaradi (yo'q "
            "bo'lsa avtomatik yaratadi)."
        ),
    ),
    patch=extend_schema(
        tags=["Sozlamalar"],
        summary="Sozlamalarni yangilash [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining til, "
            "qorong'i rejim va bildirishnoma sozlamalarini qisman yangilaydi."
        ),
    ),
)
class SettingsView(APIView):
    """GET/PATCH /api/settings/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        obj, _ = UserSettings.objects.get_or_create(user=request.user)
        return Response(SettingsSerializer(obj).data)

    def patch(self, request):
        if not request.data:
            return Response(
                {"detail": "Yuborilgan ma'lumot bo'sh."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj, _ = UserSettings.objects.get_or_create(user=request.user)
        s = SettingsSerializer(obj, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


@extend_schema(
    tags=["Sozlamalar"],
    summary="Parolni o'zgartirish [Rol: Tizimga kirgan foydalanuvchi]",
    description=(
        "Rol: Tizimga kirgan foydalanuvchi. Joriy parolni (old_password) "
        "tekshirib, Django talablariga mos yangi parolni (new_password) "
        "o'rnatadi."
    ),
)
class ChangePasswordView(APIView):
    """POST /api/settings/change-password/ {old_password, new_password}"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = ChangePasswordSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        request.user.set_password(s.validated_data["new_password"])
        request.user.save()
        return Response({"detail": "Parol muvaffaqiyatli o'zgartirildi. Qayta kiring."})