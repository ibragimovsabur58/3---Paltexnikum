"""
Test ma'lumotlar yaratadi (rasmdagi dashboardga mos).

Ishlatish:  python manage.py seed
Login:      azizbek / test12345
"""
import random
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from hub.models import (
    Announcement, Assignment, Attendance, Goal, Grade, Group, Lesson,
    Notification, Student, Subject,
)

User = get_user_model()
PASSWORD = "test12345"


class Command(BaseCommand):
    help = "Demo ma'lumotlarni yaratadi (Aliyev Azizbek, T-23-01)"

    def handle(self, *args, **options):
        random.seed(42)
        today = timezone.localdate()

        # Eski demo foydalanuvchilarni o'chiramiz (qayta ishlatish uchun)
        User.objects.filter(username__in=["azizbek", "demo1", "demo2", "demo3", "demo4"]).delete()

        # --- Guruh va fanlar ---
        group, _ = Group.objects.get_or_create(name="T-23-01", defaults={"direction": "Dasturiy ta'minot"})
        names = [("Matematika", "Karimov A."), ("Dasturlash asoslari", "Rahimova N."),
                 ("Ingliz tili", "Smith J."), ("Fizika", "Tursunov B."),
                 ("Ma'lumotlar bazasi", "Qodirov S.")]
        subjects = {}
        for name, teacher in names:
            s, _ = Subject.objects.get_or_create(name=name, defaults={"teacher": teacher})
            s.groups.add(group)
            subjects[name] = s

        # --- Asosiy talaba ---
        user = User.objects.create_user("azizbek", password=PASSWORD,
                                        first_name="Azizbek", last_name="Aliyev",
                                        email="azizbek@example.com")
        student = Student.objects.create(user=user, student_id="20231045", group=group, course=3,
                                         phone="+998901234567", address="Toshkent")

        # --- Baholar (eng yangisi ro'yxatda birinchi chiqadi, shuning uchun teskari tartibda) ---
        for subj, score in reversed([("Matematika", 5), ("Dasturlash asoslari", 5), ("Matematika", 5),
                                     ("Dasturlash asoslari", 5), ("Dasturlash asoslari", 2)]):
            Grade.objects.create(student=student, subject=subjects[subj], score=score)

        # --- Davomat: 94 keldi, 5 qoldirilgan, 3 kechikish = 102 (92%) ---
        statuses = ["present"] * 94 + ["absent"] * 5 + ["late"] * 3
        random.shuffle(statuses)
        subj_list = list(subjects.values())
        for i, st in enumerate(statuses):
            Attendance.objects.create(student=student, subject=subj_list[i % 5],
                                      date=today - timedelta(days=i // 5), status=st)

        # --- Yaqin vazifalar ---
        for subj, title, kind, days in [
            ("Matematika", "Matematika (nazorat ishi)", "control", 2),
            ("Dasturlash asoslari", "Dasturlash (amaliy ish)", "practice", 4),
            ("Ingliz tili", "Ingliz tili (test)", "test", 6),
            ("Fizika", "Fizika (BSB)", "bsb", 1),
        ]:
            Assignment.objects.create(subject=subjects[subj], group=group, title=title,
                                      kind=kind, due_date=today + timedelta(days=days))

        # --- Dars jadvali (Dushanba-Juma) ---
        plan = {1: ["Matematika", "Dasturlash asoslari"], 2: ["Ingliz tili", "Fizika"],
                3: ["Dasturlash asoslari", "Ma'lumotlar bazasi"], 4: ["Matematika", "Fizika"],
                5: ["Ma'lumotlar bazasi", "Ingliz tili"]}
        slots = [(time(9, 0), time(10, 20)), (time(10, 30), time(11, 50))]
        for day, lst in plan.items():
            for (start, end), subj in zip(slots, lst):
                Lesson.objects.create(group=group, subject=subjects[subj], weekday=day,
                                      start_time=start, end_time=end, room=f"{random.randint(101, 320)}")

        # --- Eslatmalar, bildirishnomalar, maqsadlar ---
        Announcement.objects.create(title="Ertaga Fizika BSB bo'lib o'tadi", text="Soat 9:00, 204-xona")
        Announcement.objects.create(title="Kutubxona yangi kitoblar oldi")
        Notification.objects.create(user=user, category="grade", title="Yangi baho: Matematika — 5")
        Notification.objects.create(user=user, category="assignment", title="Fizika (BSB) ertaga")
        Notification.objects.create(user=user, category="attendance", title="Siz 1 ta darsni qoldirdingiz")
        Goal.objects.create(student=student, title="O'rtacha bahoni 4.7 ga ko'tarish")
        Goal.objects.create(student=student, title="Davomatni 95% ga yetkazish")

        # --- Reyting uchun boshqa talabalar ---
        for n, fam in enumerate(["Karimov", "Yusupova", "Toshmatov", "Ergasheva"], start=1):
            u = User.objects.create_user(f"demo{n}", password=PASSWORD, first_name=f"Talaba{n}", last_name=fam)
            st = Student.objects.create(user=u, student_id=f"2023{1050 + n}", group=group, course=3)
            for subj in subj_list:
                Grade.objects.create(student=st, subject=subj, score=random.choice([3, 4, 4, 5, 5]))

        self.stdout.write(self.style.SUCCESS(
            f"Tayyor! Login: azizbek  |  Parol: {PASSWORD}"))