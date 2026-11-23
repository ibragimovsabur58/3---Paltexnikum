from datetime import timedelta

from django.contrib.auth import update_session_auth_hash
from django.db.models import Avg, Count, Q
from django.utils import timezone

from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, extend_schema_view

from .models import (
    Announcement, Assignment, Attendance, Book, ChatMessage, Goal, Grade,
    Lesson, Notification, Student, Subject, Submission, UserSettings,
)
from .serializers import (
    AnnouncementSerializer, AssignmentSerializer, AttendanceSerializer,
    BookSerializer, ChatMessageSerializer, GoalSerializer, GradeSerializer,
    LessonSerializer, NotificationSerializer, ProfileUpdateSerializer,
    StudentSerializer, UserSettingsSerializer,
)


# ==============================================================================
# RUXSATLAR (PERMISSIONS) VA YORDAMCHI FUNKSIYALAR
# ==============================================================================

class HasStudentProfile(permissions.IsAuthenticated):
    """Rol: Talaba — faqat Student profiliga ega foydalanuvchilar uchun."""
    def has_permission(self, request, view):
        return (
            super().has_permission(request, view)
            and hasattr(request.user, "student")
        )


def attendance_summary(student):
    """Talabaning umumiy davomat statistikasini hisoblaydi."""
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


# ==============================================================================
# 1-BO'LIM: TALABA UCHUN API'LAR (Rol: Talaba -> HasStudentProfile)
# ==============================================================================

# ----------------------------------------------------------
# 1.1 BOSH SAHIFA API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema(
    tags=["Bosh sahifa"],
    summary="Bosh sahifa ma'lumotlari [Rol: Talaba]",
    description=(
        "Rol: Talaba. Talabaning bosh sahifasi uchun kerakli barcha ma'lumotlarni "
        "qaytaradi: salomlashuv, profil ma'lumotlari, umumiy statistika (davomat "
        "foizi, o'rtacha baho, fanlar soni, bajarilmagan topshiriqlar soni), "
        "davomat xulosasi, so'nggi 5 ta baho, yaqinlashayotgan 4 ta topshiriq "
        "va so'nggi 3 ta e'lon."
    ),
)
class DashboardView(APIView):
    permission_classes = [HasStudentProfile]

    def get(self, request):
        student = request.user.student
        ctx = {"request": request}
        today = timezone.localdate()

        avg = (
            Grade.objects.filter(student=student)
            .aggregate(a=Avg("score"))["a"] or 0
        )

        pending = (
            Assignment.objects.filter(
                group=student.group,
                due_date__gte=today
            )
            .exclude(submissions__student=student)
        )

        return Response({
            "greeting": {
                "full_name": request.user.get_full_name(),
                "quote": (
                    "Bilim — kelajak sari yo'l. Bugungi kichik "
                    "harakatlar ertangi katta natijalarni beradi!"
                ),
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
                Grade.objects.filter(student=student).select_related("subject")[:5],
                many=True
            ).data,
            "upcoming_assignments": AssignmentSerializer(
                pending.select_related("subject")[:4],
                many=True,
                context=ctx
            ).data,
            "announcements": AnnouncementSerializer(
                Announcement.objects.all()[:3],
                many=True
            ).data,
            "daily_message": "Bugun ham o'zingizdan eng yaxshisini bering!",
        })


# ----------------------------------------------------------
# 1.2 PROFIL API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    get=extend_schema(
        tags=["Profil"],
        summary="Profil ma'lumotlarini olish [Rol: Talaba]",
        description=(
            "Rol: Talaba. Tizimga kirgan talabaning shaxsiy ma'lumotlarini "
            "(ism-familiya, guruh va boshqa profil maydonlari) qaytaradi."
        ),
    ),
    patch=extend_schema(
        tags=["Profil"],
        summary="Profilni yangilash [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaga o'z profilidagi ruxsat etilgan shaxsiy "
            "ma'lumotlarni qisman o'zgartirish imkonini beradi."
        ),
    ),
)
class MeView(APIView):
    permission_classes = [HasStudentProfile]

    def get(self, request):
        return Response(
            StudentSerializer(
                request.user.student,
                context={"request": request}
            ).data
        )

    def patch(self, request):
        s = ProfileUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        student = s.update(request.user.student, s.validated_data)

        return Response(
            StudentSerializer(
                student,
                context={"request": request}
            ).data
        )


# ----------------------------------------------------------
# 1.3 DAVOMAT API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Davomat"],
        summary="Davomatlar ro'yxati [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning barcha davomat yozuvlarini fanlar kesimida "
            "qaytaradi (kelgan, kelmagan va kechikkan kunlar)."
        ),
    ),
)
class AttendanceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        return (
            Attendance.objects
            .filter(student=self.request.user.student)
            .select_related("subject")
        )

    @extend_schema(
        tags=["Davomat"],
        summary="Davomat statistikasi [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning umumiy davomat foizi, kelgan kunlar, "
            "qoldirilgan kunlar va kechikishlar sonini qaytaradi."
        ),
    )
    @action(detail=False)
    def summary(self, request):
        return Response(attendance_summary(request.user.student))

    @extend_schema(
        tags=["Davomat"],
        summary="Davomat fanlar kesimida [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning davomat ko'rsatkichlarini har bir fan "
            "bo'yicha alohida hisoblab qaytaradi."
        ),
    )
    @action(detail=False, url_path="by-subject")
    def by_subject(self, request):
        student = request.user.student
        subjects = Subject.objects.filter(groups=student.group)
        result = []

        for subj in subjects:
            qs = Attendance.objects.filter(student=student, subject=subj)
            c = qs.aggregate(
                present=Count("id", filter=Q(status="present")),
                absent=Count("id", filter=Q(status="absent")),
                late=Count("id", filter=Q(status="late")),
                total=Count("id"),
            )
            percent = round(c["present"] / c["total"] * 100) if c["total"] else 0
            result.append({
                "subject_id": subj.id,
                "subject_name": subj.name,
                "percent": percent,
                "keldi": c["present"],
                "qoldirilgan": c["absent"],
                "kechikish": c["late"],
                "total": c["total"],
            })

        return Response(result)

    @extend_schema(
        tags=["Davomat"],
        summary="Davomat kalendari [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning davomat yozuvlarini kalendar tartibida "
            "(sana bo'yicha) qaytaradi."
        ),
    )
    @action(detail=False)
    def calendar(self, request):
        qs = self.get_queryset().order_by("-date")
        return Response(self.get_serializer(qs, many=True).data)


# ----------------------------------------------------------
# 1.4 BAHOLAR API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Baholar"],
        summary="Baholar ro'yxati [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning barcha fanlardan olgan baholarini qaytaradi. "
            "Ixtiyoriy ?subject=<id> parametri orqali ma'lum bir fan baholarini "
            "filtrlash mumkin."
        ),
    ),
)
class GradeViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = GradeSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        qs = (
            Grade.objects
            .filter(student=self.request.user.student)
            .select_related("subject")
        )
        subject = self.request.query_params.get("subject")
        return qs.filter(subject_id=subject) if subject else qs


# ----------------------------------------------------------
# 1.5 TOPSHIRIQLAR API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Topshiriqlar"],
        summary="Topshiriqlar ro'yxati [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning guruhiga biriktirilgan barcha "
            "topshiriqlarni qaytaradi."
        ),
    ),
    retrieve=extend_schema(
        tags=["Topshiriqlar"],
        summary="Bitta topshiriq haqida ma'lumot [Rol: Talaba]",
        description=(
            "Rol: Talaba. Tanlangan topshiriqning batafsil ma'lumotlarini "
            "qaytaradi."
        ),
    ),
)
class AssignmentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    serializer_class = AssignmentSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        return (
            Assignment.objects
            .filter(group=self.request.user.student.group)
            .select_related("subject")
        )

    @extend_schema(
        tags=["Topshiriqlar"],
        summary="Topshiriqni yuborish [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talaba tanlangan topshiriq uchun fayl (file) yoki "
            "izoh (comment) yuborishi mumkin (kamida bittasi bo'lishi shart). "
            "Oldin yuborilgan bo'lsa yangilanadi, aks holda yangi yozuv yaratiladi."
        ),
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        assignment = self.get_object()
        file = request.data.get("file")
        comment = str(request.data.get("comment") or "").strip()

        if not file and not comment:
            return Response(
                {"detail": "Fayl yoki izoh yuboring."},
                status=status.HTTP_400_BAD_REQUEST
            )

        _, created = Submission.objects.update_or_create(
            assignment=assignment,
            student=request.user.student,
            defaults={
                "comment": comment,
                **({"file": file} if file else {}),
            },
        )

        return Response(
            {"detail": "Topshirildi"},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


# ----------------------------------------------------------
# 1.6 DARS JADVALI API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Dars jadvali"],
        summary="Dars jadvali [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning guruhiga tegishli dars jadvalini qaytaradi. "
            "Ixtiyoriy ?weekday=<kun> parametri orqali hafta kuni bo'yicha "
            "filtrlash mumkin."
        ),
    ),
)
class LessonViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = LessonSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        qs = (
            Lesson.objects
            .filter(group=self.request.user.student.group)
            .select_related("subject")
        )
        day = self.request.query_params.get("weekday")
        return qs.filter(weekday=day) if day else qs

    @extend_schema(
        tags=["Dars jadvali"],
        summary="Bugungi darslar [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning bugungi kun uchun belgilangan darslarini "
            "qaytaradi."
        ),
    )
    @action(detail=False)
    def today(self, request):
        qs = self.get_queryset().filter(
            weekday=timezone.localdate().isoweekday()
        )
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(
        tags=["Dars jadvali"],
        summary="Keyingi dars [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning bugungi kunda boshlanish vaqti hozirgi "
            "vaqtdan keyin bo'lgan navbatdagi darsini qaytaradi."
        ),
    )
    @action(detail=False)
    def next(self, request):
        now_time = timezone.localtime().time()
        weekday = timezone.localdate().isoweekday()
        lesson = (
            self.get_queryset()
            .filter(weekday=weekday, start_time__gte=now_time)
            .order_by("start_time")
            .first()
        )
        if not lesson:
            return Response({"detail": "Keyingi dars topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(lesson).data)

    @extend_schema(
        tags=["Dars jadvali"],
        summary="Haftalik dars jadvali [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning to'liq haftalik dars jadvalini hafta "
            "kuni va boshlanish vaqti bo'yicha tartiblab qaytaradi."
        ),
    )
    @action(detail=False)
    def week(self, request):
        qs = self.get_queryset().order_by("weekday", "start_time")
        return Response(self.get_serializer(qs, many=True).data)


# ----------------------------------------------------------
# 1.7 REYTING API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema(
    tags=["Reyting"],
    summary="Talabalar reytingi [Rol: Talaba]",
    description=(
        "Rol: Talaba. Talabalarning o'rtacha baholari asosida reytingni "
        "qaytaradi: talabaning o'z o'rni (my_rank) va eng yuqori natijaga ega "
        "20 nafar talaba (top). ?scope=group parametri yuborilsa, faqat o'z "
        "guruhi ichidagi reyting hisoblanadi."
    ),
)
class RatingView(APIView):
    permission_classes = [HasStudentProfile]

    def get(self, request):
        me = request.user.student

        qs = (
            Student.objects
            .select_related("user")
            .annotate(avg=Avg("grades__score"))
            .order_by("-avg", "id")
        )

        if request.query_params.get("scope") == "group":
            qs = qs.filter(group=me.group)

        top = []
        my_rank = None

        for i, s in enumerate(qs, start=1):
            if s.pk == me.pk:
                my_rank = i

            if i <= 20:
                top.append({
                    "rank": i,
                    "full_name": s.user.get_full_name(),
                    "average": round(s.avg or 0, 2),
                    "is_me": s.pk == me.pk,
                })

        return Response({
            "my_rank": my_rank,
            "top": top
        })


# ----------------------------------------------------------
# 1.8 GURUH CHATI API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Guruh chati"],
        summary="Guruh xabarlarini olish [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning o'z guruhiga tegishli chat xabarlarini "
            "qaytaradi."
        ),
    ),
    create=extend_schema(
        tags=["Guruh chati"],
        summary="Yangi xabar yuborish [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaga o'z guruh chatiga yangi xabar yuborish "
            "imkonini beradi."
        ),
    ),
)
class ChatViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    serializer_class = ChatMessageSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        return (
            ChatMessage.objects
            .filter(group=self.request.user.student.group)
            .select_related("sender")
        )

    def perform_create(self, serializer):
        serializer.save(
            sender=self.request.user,
            group=self.request.user.student.group
        )


# ----------------------------------------------------------
# 1.9 MAQSADLAR API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Maqsadlar"],
        summary="Maqsadlar ro'yxati [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talabaning o'ziga tegishli barcha shaxsiy maqsadlarini "
            "qaytaradi."
        ),
    ),
    retrieve=extend_schema(
        tags=["Maqsadlar"],
        summary="Bitta maqsad haqida ma'lumot [Rol: Talaba]",
        description=(
            "Rol: Talaba. Tanlangan maqsadning batafsil ma'lumotlarini "
            "qaytaradi."
        ),
    ),
    create=extend_schema(
        tags=["Maqsadlar"],
        summary="Yangi maqsad yaratish [Rol: Talaba]",
        description=(
            "Rol: Talaba. Talaba uchun yangi shaxsiy maqsad qo'shadi."
        ),
    ),
    update=extend_schema(
        tags=["Maqsadlar"],
        summary="Maqsadni to'liq yangilash [Rol: Talaba]",
        description=(
            "Rol: Talaba. Tanlangan maqsad ma'lumotlarini to'liq yangilaydi."
        ),
    ),
    partial_update=extend_schema(
        tags=["Maqsadlar"],
        summary="Maqsadni qisman yangilash [Rol: Talaba]",
        description=(
            "Rol: Talaba. Tanlangan maqsadning ayrim maydonlarini o'zgartiradi."
        ),
    ),
    destroy=extend_schema(
        tags=["Maqsadlar"],
        summary="Maqsadni o'chirish [Rol: Talaba]",
        description="Rol: Talaba. Tanlangan maqsadni o'chiradi.",
    ),
)
class GoalViewSet(viewsets.ModelViewSet):
    serializer_class = GoalSerializer
    permission_classes = [HasStudentProfile]

    def get_queryset(self):
        return Goal.objects.filter(student=self.request.user.student)

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student)


# ----------------------------------------------------------
# 1.10 QIDIRUV API | Rol: Talaba
# ----------------------------------------------------------
@extend_schema(
    tags=["Qidiruv"],
    summary="Platformadan ma'lumot qidirish [Rol: Talaba]",
    description=(
        "Rol: Talaba. Majburiy ?q=<so'z> parametri orqali talaba guruhiga "
        "tegishli fanlar, topshiriqlar (maksimum 10 ta) va kutubxonadagi "
        "kitoblar (maksimum 10 ta) orasidan qidiruv natijalarini qaytaradi."
    ),
)
class SearchView(APIView):
    permission_classes = [HasStudentProfile]

    def get(self, request):
        q = request.query_params.get("q", "").strip()

        if not q:
            return Response(
                {"detail": "Qidiruv so'zi (q) yuborilmagan."},
                status=status.HTTP_400_BAD_REQUEST
            )

        student = request.user.student

        return Response({
            "subjects": list(
                Subject.objects
                .filter(groups=student.group, name__icontains=q)
                .values("id", "name", "teacher")
            ),
            "assignments": AssignmentSerializer(
                Assignment.objects.filter(group=student.group, title__icontains=q)[:10],
                many=True,
                context={"request": request}
            ).data,
            "books": BookSerializer(
                Book.objects.filter(title__icontains=q)[:10],
                many=True
            ).data,
        })


# ==============================================================================
# 2-BO'LIM: TIZIMGA KIRGAN FOYDALANUVCHI API'LARI (Rol: IsAuthenticated)
# ==============================================================================

# ----------------------------------------------------------
# 2.1 E'LONLAR API | Rol: Tizimga kirgan foydalanuvchi
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["E'lonlar"],
        summary="E'lonlar ro'yxati [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Platformada joylashtirilgan "
            "barcha e'lonlar ro'yxatini qaytaradi."
        ),
    ),
)
class AnnouncementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]


# ----------------------------------------------------------
# 2.2 BILDIRISHNOMALAR API | Rol: Tizimga kirgan foydalanuvchi
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Bildirishnomalar"],
        summary="Bildirishnomalar ro'yxati [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Tizimga kirgan "
            "foydalanuvchining o'z bildirishnomalarini qaytaradi."
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
        summary="Bildirishnomani yangilash [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Tanlangan bildirishnoma "
            "ma'lumotlarini (masalan, o'qilganlik holatini) qisman yangilaydi."
        ),
    ),
    destroy=extend_schema(
        tags=["Bildirishnomalar"],
        summary="Bildirishnomani o'chirish [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Tanlangan bildirishnomani "
            "o'chiradi."
        ),
    ),
)
class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "post", "delete", "head", "options"]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @extend_schema(
        tags=["Bildirishnomalar"],
        summary="Barcha bildirishnomalarni o'qilgan deb belgilash [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining barcha "
            "bildirishnomalarini o'qilgan (is_read=True) qiladi."
        ),
    )
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        self.get_queryset().update(is_read=True)
        return Response({"detail": "OK"})

    @extend_schema(
        tags=["Bildirishnomalar"],
        summary="O'qilgan bildirishnomalarni o'chirish [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining barcha "
            "o'qilgan (is_read=True) bildirishnomalarini o'chirib tashlaydi."
        ),
    )
    @action(detail=False, methods=["delete"], url_path="clear-read")
    def clear_read(self, request):
        deleted_count, _ = self.get_queryset().filter(is_read=True).delete()
        return Response({"deleted": deleted_count})

    @extend_schema(
        tags=["Bildirishnomalar"],
        summary="O'qilmagan bildirishnomalar soni [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining hali "
            "o'qilmagan (is_read=False) bildirishnomalari sonini qaytaradi."
        ),
    )
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"unread_count": count})


# ----------------------------------------------------------
# 2.3 KUTUBXONA API | Rol: Tizimga kirgan foydalanuvchi
# ----------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        tags=["Kutubxona"],
        summary="Kitoblar ro'yxati [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Kutubxonadagi kitoblar "
            "ro'yxatini qaytaradi. Ixtiyoriy ?q=<matn> parametri orqali kitob "
            "nomi yoki muallifi bo'yicha qidirish mumkin."
        ),
    ),
)
class BookViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = BookSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        q = self.request.query_params.get("q", "")
        return Book.objects.filter(
            Q(title__icontains=q) | Q(author__icontains=q)
        )


# ----------------------------------------------------------
# 2.4 SOZLAMALAR API | Rol: Tizimga kirgan foydalanuvchi
# ----------------------------------------------------------
@extend_schema_view(
    get=extend_schema(
        tags=["Sozlamalar"],
        summary="Foydalanuvchi sozlamalarini olish [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchining til, "
            "qorong'i rejim va bildirishnomalarga oid sozlamalarini qaytaradi."
        ),
    ),
    patch=extend_schema(
        tags=["Sozlamalar"],
        summary="Sozlamalarni yangilash [Rol: Tizimga kirgan foydalanuvchi]",
        description=(
            "Rol: Tizimga kirgan foydalanuvchi. Foydalanuvchiga til, "
            "qorong'i rejim va bildirishnoma sozlamalarini qisman o'zgartirish "
            "imkonini beradi."
        ),
    ),
)
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


@extend_schema(
    tags=["Sozlamalar"],
    summary="Parolni o'zgartirish [Rol: Tizimga kirgan foydalanuvchi]",
    description=(
        "Rol: Tizimga kirgan foydalanuvchi. Joriy parolni (old_password) "
        "tekshirib, foydalanuvchi parolini yangi parolga (new_password) "
        "o'zgartiradi."
    ),
)
class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        old_password = request.data.get("old_password") or ""
        new_password = request.data.get("new_password") or ""

        if not old_password or not new_password:
            return Response(
                {"detail": "old_password va new_password yuborilishi shart."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(old_password):
            return Response(
                {"detail": "Joriy parol noto'g'ri."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {"detail": "Yangi parol kamida 8 ta belgidan iborat bo'lishi kerak."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)

        return Response({"detail": "Parol muvaffaqiyatli o'zgartirildi."})