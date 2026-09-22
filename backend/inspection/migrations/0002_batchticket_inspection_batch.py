import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inspection", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BatchTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ticket_no", models.CharField(blank=True, max_length=40, unique=True, verbose_name="批次票号")),
                ("status", models.CharField(choices=[("success", "成功"), ("failed", "失败")], max_length=10, verbose_name="状态")),
                ("light_count", models.PositiveIntegerField(default=0, verbose_name="灯座数")),
                ("row_ids", models.TextField(blank=True, default="", verbose_name="本批新行主键串")),
                ("failed_row", models.PositiveIntegerField(blank=True, null=True, verbose_name="失败行号")),
                ("reason", models.CharField(blank=True, default="", max_length=200, verbose_name="失败原因")),
                ("created_by", models.CharField(max_length=64, verbose_name="登记人")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-id"],
            },
        ),
        migrations.AddField(
            model_name="inspection",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="inspections",
                to="inspection.batchticket",
                verbose_name="所属批次",
            ),
        ),
    ]
