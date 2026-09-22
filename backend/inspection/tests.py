from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from inspection.models import BatchTicket, Inspection


class BatchFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        inspectors = Group.objects.create(name="inspector")
        cls.keeper = User.objects.create_user("keeper", password="x")
        cls.keeper.groups.add(inspectors)
        cls.watch = User.objects.create_user("watch", password="x")

    def _batch_payload(self, rows, required="1200"):
        data = {"required_cd": required, "aid_code": [], "measured_cd": [], "bearing_error_deg": []}
        for code, measured, bearing in rows:
            data["aid_code"].append(code)
            data["measured_cd"].append(measured)
            data["bearing_error_deg"].append(bearing)
        return data

    def test_success_batch_judges_each_light_and_issues_ticket(self):
        self.client.force_login(self.keeper)
        before = Inspection.objects.count()
        payload = self._batch_payload(
            [("LH-10", "1500", "0.4"), ("LH-11", "800", "0.2")]
        )
        resp = self.client.post(reverse("batch_create"), payload)
        self.assertEqual(resp.status_code, 302)

        ticket = BatchTicket.objects.get(status=BatchTicket.Status.SUCCESS)
        self.assertTrue(ticket.ticket_no.startswith("B"))
        self.assertRedirects(resp, reverse("batch_detail", args=[ticket.pk]))
        self.assertEqual(Inspection.objects.count(), before + 2)

        rows = list(ticket.inspections.order_by("id"))
        self.assertEqual([r.aid_code for r in rows], ["LH-10", "LH-11"])
        self.assertEqual(rows[0].verdict, "合格")
        self.assertEqual(rows[1].verdict, "不合格")
        self.assertEqual(rows[1].note, "光强不足")
        self.assertEqual([r.batch_id for r in rows], [ticket.pk, ticket.pk])
        self.assertEqual(ticket.pk_list, [r.pk for r in rows])

        page = self.client.get(reverse("batch_detail", args=[ticket.pk]))
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn(ticket.ticket_no, body)
        self.assertIn("合格", body)
        self.assertIn("光强不足", body)

        lookup = self.client.get(reverse("batch_list"), {"ticket_no": ticket.ticket_no})
        self.assertEqual(lookup.status_code, 200)
        self.assertIn("LH-10", lookup.content.decode())
        self.assertIn("LH-11", lookup.content.decode())

    def test_blank_aid_code_aborts_whole_batch_and_records_attempt(self):
        self.client.force_login(self.keeper)
        before = Inspection.objects.count()
        payload = self._batch_payload(
            [("LH-20", "1500", "0.0"), ("", "800", "0.0")]
        )
        resp = self.client.post(reverse("batch_create"), payload)
        self.assertEqual(resp.status_code, 302)

        failed = BatchTicket.objects.get(status=BatchTicket.Status.FAILED)
        self.assertTrue(failed.ticket_no.startswith("F"))
        self.assertEqual(failed.failed_row, 2)
        self.assertIn("第 2 行", failed.reason)
        self.assertEqual(failed.row_ids, "")
        self.assertEqual(Inspection.objects.count(), before)
        self.assertRedirects(resp, reverse("batch_detail", args=[failed.pk]))

        page = self.client.get(reverse("batch_detail", args=[failed.pk]))
        self.assertIn("整批未入库", page.content.decode())
        attempts = self.client.get(reverse("batch_attempts"))
        self.assertIn(failed.ticket_no, attempts.content.decode())

    def test_trailing_blank_rows_are_ignored(self):
        self.client.force_login(self.keeper)
        payload = self._batch_payload(
            [("LH-30", "1500", "0.0"), ("", "", ""), ("", "", "")]
        )
        self.client.post(reverse("batch_create"), payload)
        ticket = BatchTicket.objects.get(status=BatchTicket.Status.SUCCESS)
        self.assertEqual(ticket.light_count, 1)

    def test_batch_form_and_list_render(self):
        self.client.force_login(self.keeper)
        form = self.client.get(reverse("batch_create"))
        self.assertEqual(form.status_code, 200)
        self.assertContains(form, 'name="aid_code"', count=4)

        self.client.post(
            reverse("batch_create"),
            self._batch_payload([("LH-60", "1500", "0.0")]),
        )
        ticket = BatchTicket.objects.get()
        listing = self.client.get(reverse("list"))
        self.assertContains(listing, ticket.ticket_no)
        self.assertContains(listing, "LH-60")

    def test_readonly_account_cannot_open_batch_form(self):
        self.client.force_login(self.watch)
        self.assertEqual(self.client.get(reverse("batch_create")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("batch_create"),
                self._batch_payload([("LH-40", "1500", "0")]),
            ).status_code,
            403,
        )
        self.assertEqual(Inspection.objects.filter(aid_code="LH-40").count(), 0)

    def test_readonly_account_sees_success_tickets_but_not_attempts(self):
        self.client.force_login(self.keeper)
        self.client.post(
            reverse("batch_create"),
            self._batch_payload([("LH-50", "1500", "0.0"), ("LH-51", "700", "0.0")]),
        )
        self.client.post(
            reverse("batch_create"),
            self._batch_payload([("", "1500", "0.0")]),
        )
        success = BatchTicket.objects.get(status=BatchTicket.Status.SUCCESS)
        failed = BatchTicket.objects.get(status=BatchTicket.Status.FAILED)

        self.client.force_login(self.watch)
        self.assertEqual(self.client.get(reverse("batch_list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("batch_detail", args=[success.pk])).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("batch_detail", args=[failed.pk])).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("batch_attempts")).status_code, 403)
        lookup = self.client.get(reverse("batch_list"), {"ticket_no": failed.ticket_no})
        self.assertIn("查无票号", lookup.content.decode())
