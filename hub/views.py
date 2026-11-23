from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Announcement, Assignment, Attendance, Book, ChatMessage, Goal, Grade,
    Lesson, Notification, Student, Subject, Submission, UserSettings,
)
from .serializers import (
    AnnouncementSerializer, AssignmentSerializer, AttendanceSerializer,
    BookSerializer, ChatMessageSerializer, GoalSerializer, GradeSerializer,
    LessonSerializer, NotificationSerializer, ProfileUpdateSerializer,
    StudentSerializer, SubmissionSerializer, UserSettingsSerializer,
)


class HasStudentProfile(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and hasattr(request.user, "student")


def attendance_summary(student):
    qs = Attendance.objects.filter(student=student)
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
    }


class DashboardView(APIView):
    """Bosh sahifa uchun barcha ma'lumotlar bitta so'rovda."""
    permission_classes = [HasStudentProfile]

    def get(self, request):
        student = request.user.student
        ctx = {"request": request}
        today = timezone.localdate()

        avg = Grade.objects.filter(student=student).aggregate(a=Avg("score"))["a"] or 0
        pending = (
            Assignment.objects.filter(group=student.group, due_date__gte=today)
            .exclude(submissions__student=student)
        )

        return Response({
            "greeting": {
                "full_name": request.user.get_full_name(),
                "quote": "Bilim — kelajak sari yo'l. Bugungi kichik harakatlar ertangi katta natijalarni beradi!",
            },
            "profile": StudentSerializer(student, context=ctx).data,
            "stats": {
                "attendance_percent": attendance_summary(student)["percent"],
                "average_grade": round(avg, 1),
                "subjects_count": Subject.objects.filter(groups=student.group).count(),
                "pending_assignments": pending.count(),
            },
            "attendance": attendance_summary(student),
            "recent_grades": GradeSerializer(
                Grade.objects.filter(student=student).select_related("subject")[:5], many=True
            ).data,
            "upcoming_assignments": AssignmentSerializer(
                pending.select_related("subject")[:4], many=True, context=ctx
            ).data,
            "announcements": AnnouncementSerializer(Announcement.objects.all()[:3], many=True).data,
            "daily_message": "Bugun ham o'zingizdan eng yaxshisini bering!",
        })


class MeView(APIView):
    permission_classes = [HasStudentProfile]

    def get(self, request):
        return Response(StudentSerializer(request.user.student, context={"request": request}).data)

    def patch(self, request):
        s = ProfileUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        student = s.update(request.user.student, s.validated_data)
        return Response(StudentSerializer(student, context={"request": request}).data)


class AttendanceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        return Attendance.objects.filter(student=self.request.user.student).select_related("subject")

    @action(detail=False)
    def summary(self, request):
        return Response(attendance_summary(request.user.student))


class GradeViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = GradeSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        qs = Grade.objects.filter(student=self.request.user.student).select_related("subject")
        subject = self.request.query_params.get("subject")
        return qs.filter(subject_id=subject) if subject else qs


class AssignmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Amaliyot / vazifalar"""
    serializer_class = AssignmentSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        return Assignment.objects.filter(group=self.request.user.student.group).select_related("subject")

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        assignment = self.get_object()
        file = request.data.get("file")
        comment = str(request.data.get("comment") or "").strip()
        if not file and not comment:
            return Response({"detail": "Fayl yoki izoh yuboring."},
                            status=status.HTTP_400_BAD_REQUEST)
        _, created = Submission.objects.update_or_create(
            assignment=assignment, student=request.user.student,
            defaults={"comment": comment, **({"file": file} if file else {})},
        )
        return Response({"detail": "Topshirildi"},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class LessonViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = LessonSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        qs = Lesson.objects.filter(group=self.request.user.student.group).select_related("subject")
        day = self.request.query_params.get("weekday")
        return qs.filter(weekday=day) if day else qs

    @action(detail=False)
    def today(self, request):
        qs = self.get_queryset().filter(weekday=timezone.localdate().isoweekday())
        return Response(self.get_serializer(qs, many=True).data)


class RatingView(APIView):
    """Reyting: o'rtacha baho bo'yicha."""
    permission_classes = [HasStudentProfile]

    def get(self, request):
        me = request.user.student
        qs = (
            Student.objects.select_related("user")
            .annotate(avg=Avg("grades__score"))
            .order_by("-avg", "id")
        )
        if request.query_params.get("scope") == "group":
            qs = qs.filter(group=me.group)

        top, my_rank = [], None
        for i, s in enumerate(qs, start=1):
            if s.pk == me.pk:
                my_rank = i
            if i <= 20:
                top.append({"rank": i, "full_name": s.user.get_full_name(),
                            "average": round(s.avg or 0, 2), "is_me": s.pk == me.pk})
        return Response({"my_rank": my_rank, "top": top})


class AnnouncementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]


class NotificationViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        self.get_queryset().update(is_read=True)
        return Response({"detail": "OK"})


class BookViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = BookSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        q = self.request.query_params.get("q", "")
        return Book.objects.filter(Q(title__icontains=q) | Q(author__icontains=q))


class ChatViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Guruh chat (oddiy REST; real-time uchun Channels qo'shish mumkin)."""
    serializer_class = ChatMessageSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        return ChatMessage.objects.filter(group=self.request.user.student.group).select_related("sender")

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user, group=self.request.user.student.group)


class GoalViewSet(viewsets.ModelViewSet):
    serializer_class = GoalSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        return Goal.objects.filter(student=self.request.user.student)

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student)


class SettingsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        obj, _ = UserSettings.objects.get_or_create(user=request.user)
        return Response(UserSettingsSerializer(obj).data)

    def patch(self, request):
        obj, _ = UserSettings.objects.get_or_create(user=request.user)
        s = UserSettingsSerializer(obj, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


class SearchView(APIView):
    """Yuqoridagi qidiruv: fan yoki bo'lim nomi bo'yicha."""
    permission_classes = [HasStudentProfile]

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if not q:
            return Response({"detail": "Qidiruv so'zi (q) yuborilmagan."},
                            status=status.HTTP_400_BAD_REQUEST)
        student = request.user.student
        return Response({
            "subjects": list(Subject.objects.filter(groups=student.group, name__icontains=q)
                             .values("id", "name", "teacher")),
            "assignments": AssignmentSerializer(
                Assignment.objects.filter(group=student.group, title__icontains=q)[:10],
                many=True, context={"request": request}).data,
            "books": BookSerializer(Book.objects.filter(title__icontains=q)[:10], many=True).data,
        })