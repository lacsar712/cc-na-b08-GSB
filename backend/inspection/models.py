from django.db import models


class BatchAttempt(models.Model):
    """一次批量提交：成功则签发批次票，失败则留下失败尝试。"""

    ticket = models.CharField("批次票号", max_length=40, unique=True, null=True, blank=True)
    status = models.CharField("状态", max_length=10)  # success / failed
    submitted_rows = models.PositiveIntegerField("提交行数")
    failed_row = models.PositiveIntegerField("问题行号", null=True, blank=True)
    fail_reason = models.CharField("失败原因", max_length=200, blank=True)
    row_keys = models.TextField("本批新行主键串", blank=True)
    created_by = models.CharField("提交人", max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    @property
    def row_id_list(self) -> list[int]:
        return [int(part) for part in self.row_keys.split(",") if part]


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
        BatchAttempt,
        verbose_name="所属批次",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspections",
    )

    class Meta:
        ordering = ["-id"]
