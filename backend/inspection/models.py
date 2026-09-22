from django.db import models


class BatchTicket(models.Model):
    """一次批量登记的票：整批成功时为正式批次票，校验失败时为失败尝试。"""

    class Status(models.TextChoices):
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"

    ticket_no = models.CharField("批次票号", max_length=40, unique=True, blank=True)
    status = models.CharField("状态", max_length=10, choices=Status.choices)
    light_count = models.PositiveIntegerField("灯座数", default=0)
    row_ids = models.TextField("本批新行主键串", blank=True, default="")
    failed_row = models.PositiveIntegerField("失败行号", null=True, blank=True)
    reason = models.CharField("失败原因", max_length=200, blank=True, default="")
    created_by = models.CharField("登记人", max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.ticket_no

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.ticket_no:
            prefix = "B" if self.status == self.Status.SUCCESS else "F"
            self.ticket_no = f"{prefix}{self.id:08d}"
            super().save(update_fields=["ticket_no"])

    @property
    def pk_list(self) -> list[int]:
        return [int(x) for x in self.row_ids.split(",") if x]


class Inspection(models.Model):
    aid_code = models.CharField("航标编号", max_length=40)
    measured_cd = models.FloatField("实测光强")
    required_cd = models.FloatField("要求光强")
    bearing_error_deg = models.FloatField("方位偏差")
    verdict = models.CharField("结论", max_length=20)
    note = models.CharField("说明", max_length=200)
    created_by = models.CharField("登记人", max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    batch = models.ForeignKey(
        BatchTicket,
        verbose_name="所属批次",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspections",
    )

    class Meta:
        ordering = ["-id"]
