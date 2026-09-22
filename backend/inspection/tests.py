from django.contrib.auth.models import Group, User
from django.test import TestCase

from inspection.models import BatchAttempt, Inspection

FORM_FIELDS = ["measured_cd", "required_cd", "bearing_error_deg"]


class BatchInspectionTests(TestCase):
    def setUp(self):
        group = Group.objects.create(name="inspector")
        self.keeper = User.objects.create_user("keeper", password="x")
        self.keeper.groups.add(group)
        self.watch = User.objects.create_user("watch", password="x")

    def _batch_post(self, client, rows):
        """rows: [(aid_code, measured, required, bearing), ...]"""
        payload = {
            "aid_code": [r[0] for r in rows],
            "measured_cd": [str(r[1]) for r in rows],
            "required_cd": [str(r[2]) for r in rows],
            "bearing_error_deg": [str(r[3]) for r in rows],
        }
        return client.post("/batch/new/", payload)

    def test_one_pass_one_dim_same_ticket(self):
        self.client.force_login(self.keeper)
        resp = self._batch_post(self.client, [("LH-B1", 1400, 1200, 0.4), ("LH-B2", 800, 1200, 0.2)])
        self.assertEqual(resp.status_code, 200)
        attempt = resp.context["attempt"]
        self.assertTrue(attempt.succeeded)
        self.assertTrue(attempt.ticket.startswith("B"))
        lines = resp.context["lines"]
        self.assertEqual([l["row"].verdict for l in lines], ["合格", "不合格"])
        self.assertEqual(lines[0]["row"].note, "光强与方位均在限内")
        self.assertEqual(lines[1]["row"].note, "光强不足")
        # 总表新增两行，同一票号
        self.assertEqual(Inspection.objects.count(), 2)
        tickets = {r.batch.ticket for r in Inspection.objects.all()}
        self.assertEqual(tickets, {attempt.ticket})
        # 行主键串把本批新行串在一起
        self.assertEqual(
            attempt.row_id_list,
            list(Inspection.objects.order_by("id").values_list("id", flat=True)),
        )
        # 按票号回看
        view = self.client.get(f"/batch/{attempt.ticket}/")
        self.assertEqual(view.status_code, 200)
        self.assertEqual(len(view.context["rows"]), 2)

    def test_blank_aid_code_aborts_whole_batch(self):
        self.client.force_login(self.keeper)
        # 先成功一批，确认行数基线
        self._batch_post(self.client, [("LH-OK1", 1400, 1200, 0), ("LH-OK2", 1500, 1200, 0)])
        self.assertEqual(Inspection.objects.count(), 2)
        # 第二行灯号空白
        resp = self._batch_post(self.client, [("LH-C1", 1400, 1200, 0), ("", 900, 1200, 0)])
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["failed"])
        self.assertEqual(resp.context["line_no"], 2)
        # 总表行数不变
        self.assertEqual(Inspection.objects.count(), 2)
        # 留下一条失败尝试，无新实测行、无票号
        failed = BatchAttempt.objects.get(status="failed")
        self.assertEqual(failed.failed_row, 2)
        self.assertIn("灯号空白", failed.fail_reason)
        self.assertFalse(failed.ticket)
        self.assertEqual(failed.row_keys, "")
        self.assertEqual(failed.inspections.count(), 0)

    def test_readonly_cannot_open_batch_form(self):
        self.client.force_login(self.watch)
        self.assertEqual(self.client.get("/batch/new/").status_code, 403)
        resp = self._batch_post(self.client, [("LH-X", 1400, 1200, 0), ("LH-Y", 800, 1200, 0)])
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Inspection.objects.count(), 0)
        # 失败尝试页也不开放
        self.assertEqual(self.client.get("/batch/failed/").status_code, 403)

    def test_readonly_can_view_successful_tickets(self):
        self.client.force_login(self.keeper)
        resp = self._batch_post(self.client, [("LH-R1", 1400, 1200, 0), ("LH-R2", 800, 1200, 0)])
        ticket = resp.context["attempt"].ticket
        self.client.force_login(self.watch)
        self.assertEqual(self.client.get("/batch/tickets/").status_code, 200)
        view = self.client.get(f"/batch/{ticket}/")
        self.assertEqual(view.status_code, 200)
        self.assertEqual({r.aid_code for r in view.context["rows"]}, {"LH-R1", "LH-R2"})
