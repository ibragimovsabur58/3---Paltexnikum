from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Group(models.Model):
    name = models.CharField(max_length=20, unique=True)  # T-23-01
    direction = models.CharField(max_length=100)  # Dasturiy ta'minot

    def __str__(self):
        return self.name


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student")
    student_id = models.CharField(max_length=20, unique=True)  # 20231045
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="students")
    course = models.PositiveSmallIntegerField(default=1)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True)
    birth_date = models.DateField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.student_id})"


class Subject(models.Model):
    name = models.CharField(max_length=100)
    teacher = models.CharField(max_length=100, blank=True)
    groups = models.ManyToManyField(Group, related_name="subjects")

    def __str__(self):
        return self.name


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Keldi"
        ABSENT = "absent", "Qoldirilgan"
        LATE = "late", "Kechikish"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendances")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)

    class Meta:
        unique_together = ("student", "subject", "date")
        ordering = ["-date"]


class Grade(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="grades")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField()  # 1..5
    date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]


class Assignment(models.Model):
    class Kind(models.TextChoices):
        CONTROL = "control", "Nazorat ishi"
        PRACTICE = "practice", "Amaliy ish"
        TEST = "test", "Test"
        BSB = "bsb", "BSB"

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="assignments")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    due_date = models.DateField()

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return self.title


class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="submissions")
    file = models.FileField(upload_to="submissions/", blank=True, null=True)
    comment = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("assignment", "student")


class Lesson(models.Model):  # Dars jadvali
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="lessons")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    weekday = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 8)])  # 1=Dushanba
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["weekday", "start_time"]


class Announcement(models.Model):  # Eslatmalar
    title = models.CharField(max_length=200)
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Notification(models.Model):  # Bildirishnomalar
    class Category(models.TextChoices):
        INFO = "info", "Umumiy"
        GRADE = "grade", "Baho"
        ASSIGNMENT = "assignment", "Vazifa"
        ATTENDANCE = "attendance", "Davomat"
        SYSTEM = "system", "Tizim"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.INFO)
    title = models.CharField(max_length=200)
    text = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Book(models.Model):  # Kutubxona
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=150, blank=True)
    file = models.FileField(upload_to="books/")

    def __str__(self):
        return self.title


class ChatMessage(models.Model):  # Guruh chat
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Goal(models.Model):  # Maqsadlar
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="goals")
    title = models.CharField(max_length=200)
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class UserSettings(models.Model):  # Sozlamalar
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="hub_settings")
    language = models.CharField(
        max_length=5, default="uz", choices=[("uz", "O'zbekcha"), ("ru", "Русский"), ("en", "English")]
    )
    dark_mode = models.BooleanField(default=True)
    notifications_enabled = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=False)
    deadline_reminders = models.BooleanField(default=True)
    grade_notifications = models.BooleanField(default=True)