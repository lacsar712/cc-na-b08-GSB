from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from inspection.models import BatchTicket, Inspection
from inspection.rules import judge

BATCH_ROW_SLOTS = 4


def _can_write(user) -> bool:
    return user.groups.filter(name="inspector").exists()


class BatchParseError(Exception):
    def __init__(self, message: str, row: int = 0, attempted: int = 0):
        super().__init__(message)
        self.message = message
        self.row = row
        self.attempted = attempted


def _parse_batch_post(post):
    codes = post.getlist("aid_code")
    measured = post.getlist("measured_cd")
    bearing = post.getlist("bearing_error_deg")
    try:
        required = float(post.get("required_cd", "").strip())
    except ValueError:
        raise BatchParseError("批次要求光强必须为数字")

    def cell(values, i):
        return values[i].strip() if i < len(values) else ""

    last = -1
    for i in range(len(codes)):
        if cell(codes, i) or cell(measured, i) or cell(bearing, i):
            last = i
    if last < 0:
        raise BatchParseError("请至少填写一座灯")

    rows = []
    for i in range(last + 1):
        line = i + 1
        code = cell(codes, i)
        if not code:
            raise BatchParseError(f"第 {line} 行灯号空白，整批未入库", line, last + 1)
        try:
            measured_val = float(cell(measured, i))
        except ValueError:
            raise BatchParseError(f"第 {line} 行实测亮度必须为数字", line, last + 1)
        try:
            bearing_val = float(cell(bearing, i))
        except ValueError:
            raise BatchParseError(f"第 {line} 行偏角必须为数字", line, last + 1)
        rows.append((code, measured_val, bearing_val))
    return required, rows


def health(_request):
    from django.http import JsonResponse

    return JsonResponse({"status": "ok", "service": "nav-aid-inspection"})


@require_http_methods(["GET", "POST"])
def login_view(request):
    from django.contrib.auth import authenticate, login

    error = ""
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", "").strip(),
            password=request.POST.get("password", ""),
        )
        if user is None:
            error = "用户名或密码错误"
        else:
            login(request, user)
            return redirect("list")
    return render(request, "login.html", {"error": error})


def logout_view(request):
    from django.contrib.auth import logout

    logout(request)
    return redirect("login")


@login_required
def list_view(request):
    rows = Inspection.objects.select_related("batch").all()
    return render(request, "list.html", {"rows": rows, "can_write": _can_write(request.user)})


@login_required
def detail_view(request, pk):
    row = get_object_or_404(Inspection, pk=pk)
    return render(request, "detail.html", {"row": row})


@login_required
@require_http_methods(["GET", "POST"])
def create_view(request):
    if not _can_write(request.user):
        return HttpResponseForbidden("仅巡检员可登记灯光巡检")
    error = ""
    if request.method == "POST":
        try:
            measured = float(request.POST["measured_cd"])
            required = float(request.POST["required_cd"])
            bearing = float(request.POST["bearing_error_deg"])
            code = request.POST["aid_code"].strip()
            if not code:
                raise ValueError("empty")
        except (KeyError, ValueError):
            error = "请填编号和三项数值"
        else:
            verdict, note = judge(measured, required, bearing)
            row = Inspection.objects.create(
                aid_code=code,
                measured_cd=measured,
                required_cd=required,
                bearing_error_deg=bearing,
                verdict=verdict,
                note=note,
                created_by=request.user.username,
            )
            return redirect("detail", pk=row.pk)
    return render(request, "form.html", {"error": error})


@login_required
@require_http_methods(["GET", "POST"])
def batch_create_view(request):
    if not _can_write(request.user):
        return HttpResponseForbidden("仅巡检员可打开批量登记表")

    if request.method == "GET":
        return render(
            request,
            "batch_form.html",
            {"slots": range(BATCH_ROW_SLOTS), "default_required": 1200},
        )

    try:
        required, rows = _parse_batch_post(request.POST)
    except BatchParseError as exc:
        failed = BatchTicket.objects.create(
            status=BatchTicket.Status.FAILED,
            light_count=exc.attempted,
            failed_row=exc.row or None,
            reason=exc.message,
            created_by=request.user.username,
        )
        return redirect("batch_detail", pk=failed.pk)

    with transaction.atomic():
        batch = BatchTicket.objects.create(
            status=BatchTicket.Status.SUCCESS,
            light_count=len(rows),
            created_by=request.user.username,
        )
        created = []
        for code, measured_val, bearing_val in rows:
            verdict, note = judge(measured_val, required, bearing_val)
            created.append(
                Inspection.objects.create(
                    aid_code=code,
                    measured_cd=measured_val,
                    required_cd=required,
                    bearing_error_deg=bearing_val,
                    verdict=verdict,
                    note=note,
                    created_by=request.user.username,
                    batch=batch,
                )
            )
        batch.row_ids = ",".join(str(r.pk) for r in created)
        batch.save(update_fields=["row_ids"])
    return redirect("batch_detail", pk=batch.pk)


@login_required
def batch_detail_view(request, pk):
    ticket = get_object_or_404(BatchTicket, pk=pk)
    if ticket.status == BatchTicket.Status.FAILED and not _can_write(request.user):
        return HttpResponseForbidden("只读账号不能查看失败批次尝试")
    rows = ticket.inspections.order_by("id")
    return render(request, "batch_detail.html", {"ticket": ticket, "rows": rows})


@login_required
def batch_list_view(request):
    tickets = BatchTicket.objects.filter(status=BatchTicket.Status.SUCCESS)
    q = request.GET.get("ticket_no", "").strip()
    matched = None
    lookup_error = ""
    if q:
        matched = BatchTicket.objects.filter(ticket_no=q).first()
        if matched is None or (
            matched.status == BatchTicket.Status.FAILED and not _can_write(request.user)
        ):
            matched = None
            lookup_error = f"查无票号 {q}"
    return render(
        request,
        "batch_list.html",
        {
            "tickets": tickets,
            "q": q,
            "matched": matched,
            "matched_rows": matched.inspections.order_by("id") if matched else [],
            "lookup_error": lookup_error,
        },
    )


@login_required
def batch_attempts_view(request):
    if not _can_write(request.user):
        return HttpResponseForbidden("仅巡检员可查看失败批次尝试")
    attempts = BatchTicket.objects.filter(status=BatchTicket.Status.FAILED)
    return render(request, "batch_attempts.html", {"attempts": attempts})
