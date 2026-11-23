"""
Chap menyudagi bo'limlar: Profilim, Davomat, Dars jadvali, Reyting,
Bildirishnomalar, Sozlamalar.
"""
from datetime import date, timedelta

from django.contrib.auth.password_validation import validate_password
from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Assignment, Attendance, Grade, Lesson, Notification, Student,
    Subject, Submission, UserSettings,
)

WEEKDAYS = {1: "Dushanba", 2: "Seshanba", 3: "Chorshanba", 4: "Payshanba",
            5: "Juma", 6: "Shanba", 7: "Yakshanba"}


class HasStudentProfile(permissions.IsAuthenticated):
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


# ======================================================================
# 1. PROFILIM
# ======================================================================
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


class ProfileView(APIView):
    """GET /api/profile/  — profil + statistika
       PATCH /api/profile/ — profilni tahrirlash (multipart: avatar ham bo'ladi)"""
    permission_classes = [HasStudentProfile]

    def _stats(self, student):
        att = Attendance.objects.filter(student=student).aggregate(
            total=Count("id"), present=Count("id", filter=Q(status="present")))
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
            return Response({"detail": "Yuborilgan ma'lumot bo'sh."},
                            status=status.HTTP_400_BAD_REQUEST)
        student = request.user.student
        s = ProfileSerializer(student, data=request.data, partial=True, context={"request": request})
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


# ======================================================================
# 2. DAVOMAT
# ======================================================================
class AttendanceItemSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="subject.name")
    status_display = serializers.CharField(source="get_status_display")

    class Meta:
        model = Attendance
        fields = ["id", "subject", "date", "status", "status_display"]


def _summary(qs):
    c = qs.aggregate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
        total=Count("id"),
    )
    percent = round(c["present"] / c["total"] * 100) if c["total"] else 0
    return {"percent": percent, "keldi": c["present"], "qoldirilgan": c["absent"],
            "kechikish": c["late"], "jami": c["total"]}


class AttendanceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/attendance/?month=2026-11&status=absent&subject=3
    GET /api/attendance/summary/?month=2026-11
    GET /api/attendance/by-subject/
    GET /api/attendance/calendar/?month=2026-11
    """
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

    @action(detail=False)
    def summary(self, request):
        qs = self._base()
        if request.query_params.get("month"):
            y, m = parse_month(request.query_params["month"])
            qs = qs.filter(date__year=y, date__month=m)
        return Response(_summary(qs))

    @action(detail=False, url_path="by-subject")
    def by_subject(self, request):
        subjects = Subject.objects.filter(groups=request.user.student.group)
        result = []
        for sub in subjects:
            row = _summary(self._base().filter(subject=sub))
            row.update(subject_id=sub.id, subject=sub.name)
            result.append(row)
        return Response(result)

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


# ======================================================================
# 3. DARS JADVALI
# ======================================================================
class LessonSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="subject.name")
    teacher = serializers.CharField(source="subject.teacher")
    weekday_name = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = ["id", "subject", "teacher", "weekday", "weekday_name",
                  "start_time", "end_time", "room"]

    def get_weekday_name(self, obj):
        return WEEKDAYS.get(obj.weekday)


class ScheduleViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /api/schedule/?weekday=1     — oddiy ro'yxat
    GET /api/schedule/week/          — haftalik, kunlar bo'yicha guruhlangan
    GET /api/schedule/today/         — bugungi darslar
    GET /api/schedule/next/          — keyingi dars
    """
    serializer_class = LessonSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        qs = Lesson.objects.filter(group=self.request.user.student.group).select_related("subject")
        if self.request.query_params.get("weekday"):
            qs = qs.filter(weekday=self.request.query_params["weekday"])
        return qs

    @action(detail=False)
    def week(self, request):
        today = timezone.localdate().isoweekday()
        grouped = {d: [] for d in range(1, 7)}  # Dushanba-Shanba
        for lesson in self.get_queryset():
            grouped.setdefault(lesson.weekday, []).append(self.get_serializer(lesson).data)
        return Response([
            {"weekday": d, "name": WEEKDAYS[d], "is_today": d == today, "lessons": items}
            for d, items in grouped.items()
        ])

    @action(detail=False)
    def today(self, request):
        qs = self.get_queryset().filter(weekday=timezone.localdate().isoweekday())
        return Response(self.get_serializer(qs, many=True).data)

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


# ======================================================================
# 4. REYTING
# ======================================================================
class RatingView(APIView):
    """
    GET /api/rating/?scope=group|all&subject=<id>&limit=20
    O'rtacha baho bo'yicha reyting. Teng ballar bir xil o'rin oladi.
    """
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
            qs.annotate(avg=Avg("grades__score", filter=flt),
                        grades_count=Count("grades", filter=flt))
            .filter(grades_count__gt=0)
            .order_by("-avg", "-grades_count", "id")
        )

        rows, my_row, prev_avg, prev_rank = [], None, None, 0
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


# ======================================================================
# 5. BILDIRISHNOMALAR
# ======================================================================
class NotificationSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "category", "category_display", "title", "text", "is_read", "created_at"]
        read_only_fields = ["category", "title", "text", "created_at"]


class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin, mixins.DestroyModelMixin,
                          viewsets.GenericViewSet):
    """
    GET    /api/notifications/?unread=1&category=grade
    GET    /api/notifications/unread-count/
    PATCH  /api/notifications/<id>/        {"is_read": true}
    POST   /api/notifications/read-all/
    DELETE /api/notifications/<id>/
    DELETE /api/notifications/clear-read/
    """
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
            return Response({"is_read": ["Bu maydon majburiy."]},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, url_path="unread-count")
    def unread_count(self, request):
        n = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread": n})

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        n = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"updated": n})

    @action(detail=False, methods=["delete"], url_path="clear-read")
    def clear_read(self, request):
        n, _ = Notification.objects.filter(user=request.user, is_read=True).delete()
        return Response({"deleted": n})


# ======================================================================
# 6. SOZLAMALAR
# ======================================================================
class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = ["language", "dark_mode", "notifications_enabled",
                  "email_notifications", "deadline_reminders", "grade_notifications"]


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


class SettingsView(APIView):
    """GET/PATCH /api/settings/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        obj, _ = UserSettings.objects.get_or_create(user=request.user)
        return Response(SettingsSerializer(obj).data)

    def patch(self, request):
        if not request.data:
            return Response({"detail": "Yuborilgan ma'lumot bo'sh."},
                            status=status.HTTP_400_BAD_REQUEST)
        obj, _ = UserSettings.objects.get_or_create(user=request.user)
        s = SettingsSerializer(obj, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class ChangePasswordView(APIView):
    """POST /api/settings/change-password/  {old_password, new_password}"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = ChangePasswordSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        request.user.set_password(s.validated_data["new_password"])
        request.user.save()
        return Response({"detail": "Parol muvaffaqiyatli o'zgartirildi. Qayta kiring."})