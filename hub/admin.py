from django.contrib import admin

from . import models

admin.site.register([
    models.Group, models.Subject, models.Announcement, models.Notification,
    models.Book, models.ChatMessage, models.Goal, models.UserSettings,
    models.Submission, models.Lesson,
])


@admin.register(models.Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("user", "student_id", "group", "course")
    search_fields = ("student_id", "user__first_name", "user__last_name")


@admin.register(models.Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "date", "status")
    list_filter = ("status", "subject", "date")


@admin.register(models.Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "score", "date")
    list_filter = ("subject",)


@admin.register(models.Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "group", "kind", "due_date")
    list_filter = ("kind", "group")