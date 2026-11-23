from django.utils import timezone
from rest_framework import serializers

from .models import (
    Announcement, Assignment, Attendance, Book, ChatMessage, Goal, Grade,
    Lesson, Notification, Student, Submission, UserSettings,
)


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    group = serializers.CharField(source="group.name", read_only=True)
    direction = serializers.CharField(source="group.direction", read_only=True)

    class Meta:
        model = Student
        fields = ["id", "full_name", "student_id", "group", "direction", "course", "avatar"]
        read_only_fields = ["student_id"]


class ProfileUpdateSerializer(serializers.Serializer):
    """Profilni tahrirlash"""
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    avatar = serializers.ImageField(required=False)

    def update(self, student, data):
        user = student.user
        user.first_name = data.get("first_name", user.first_name)
        user.last_name = data.get("last_name", user.last_name)
        user.save()
        if "avatar" in data:
            student.avatar = data["avatar"]
            student.save()
        return student


class AttendanceSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="subject.name")
    status_display = serializers.CharField(source="get_status_display")

    class Meta:
        model = Attendance
        fields = ["id", "subject", "date", "status", "status_display"]


class GradeSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="subject.name")

    class Meta:
        model = Grade
        fields = ["id", "subject", "score", "date"]


class AssignmentSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="subject.name")
    kind_display = serializers.CharField(source="get_kind_display")
    days_left = serializers.SerializerMethodField()
    submitted = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = ["id", "title", "subject", "kind", "kind_display", "due_date", "days_left", "submitted"]

    def get_days_left(self, obj):
        return (obj.due_date - timezone.localdate()).days

    def get_submitted(self, obj):
        student = self.context["request"].user.student
        return obj.submissions.filter(student=student).exists()


class SubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = ["id", "assignment", "file", "comment", "submitted_at"]
        read_only_fields = ["submitted_at", "assignment"]


class LessonSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="subject.name")
    teacher = serializers.CharField(source="subject.teacher")

    class Meta:
        model = Lesson
        fields = ["id", "subject", "teacher", "weekday", "start_time", "end_time", "room"]


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ["id", "title", "text", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "text", "is_read", "created_at"]
        read_only_fields = ["title", "text", "created_at"]


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ["id", "title", "author", "file"]


class ChatMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.get_full_name", read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["id", "sender", "sender_name", "text", "created_at"]
        read_only_fields = ["sender", "created_at"]


class GoalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Goal
        fields = ["id", "title", "is_done", "created_at"]
        read_only_fields = ["created_at"]


class UserSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        fields = ["language", "dark_mode", "notifications_enabled"]