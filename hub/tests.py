from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from hub.models import Assignment, Group, Notification, Student, Subject


class BadRequestTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("tester", password="test12345")
        group = Group.objects.create(name="T-1", direction="Dasturiy ta'minot")
        Student.objects.create(user=user, student_id="1", group=group, course=1)
        subject = Subject.objects.create(name="Matematika")
        subject.groups.add(group)
        self.assignment = Assignment.objects.create(
            subject=subject, group=group, title="Test", kind="test",
            due_date=timezone.localdate())
        self.notification = Notification.objects.create(user=user, title="Salom")
        self.client.force_authenticate(user)

    def test_empty_profile_patch_is_400(self):
        self.assertEqual(self.client.patch("/api/profile/", {}, format="json").status_code, 400)

    def test_empty_settings_patch_is_400(self):
        self.assertEqual(self.client.patch("/api/settings/", {}, format="json").status_code, 400)

    def test_notification_patch_without_is_read_is_400(self):
        r = self.client.patch(f"/api/notifications/{self.notification.pk}/", {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_notification_patch_with_is_read_is_200(self):
        r = self.client.patch(f"/api/notifications/{self.notification.pk}/",
                              {"is_read": True}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_bad_month_is_400(self):
        self.assertEqual(self.client.get("/api/attendance/?month=abc").status_code, 400)
        self.assertEqual(self.client.get("/api/attendance/summary/?month=2026-13").status_code, 400)

    def test_bad_rating_limit_is_400(self):
        self.assertEqual(self.client.get("/api/rating/?limit=abc").status_code, 400)

    def test_empty_search_is_400(self):
        self.assertEqual(self.client.get("/api/search/").status_code, 400)

    def test_empty_submit_is_400_and_valid_submit_is_201(self):
        url = f"/api/assignments/{self.assignment.pk}/submit/"
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"comment": "Bajarildi"}, format="json").status_code, 201)
        self.assertEqual(self.client.post(url, {"comment": "Yangilandi"}, format="json").status_code, 200)

    def test_empty_chat_and_goal_are_400(self):
        self.assertEqual(self.client.post("/api/chat/", {}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/goals/", {}, format="json").status_code, 400)

    def test_empty_login_is_400(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/auth/login/", {}, format="json").status_code, 400)