import secrets
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from inspection.models import BatchAttempt, Inspection
from inspection.rules import judge

BATCH_MIN_ROWS = 2


def _can_write(user) -> bool:
    return user.groups.filter(name="inspector").exists()


def _make_ticket() -> str:
    return "B" + datetime.now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(2).upper()


def _parse_rows(post) -> tuple[list[dict], list[tuple[int, str]], int]:
    """从数组字段解析批量行；返回 (有效行, [(表单行号, 原因)], 实际填写行数)。"""
    codes = post.getlist("aid_code")
    measured_list = post.getlist("measured_cd")
    required_list = post.getlist("required_cd")
    bearing_list = post.getlist("bearing_error_deg")
    rows, errors = [], []
    kept = 0
    for i in range(len(codes)):
        code = codes[i].strip()
        raw_measured = measured_list[i].strip() if i < len(measured_list) else ""
        raw_required = required_list[i].strip() if i < len(required_list) else ""
        raw_bearing = bearing_list[i].strip() if i < len(bearing_list) else ""
        # 整行全空（多半是多按出来没填的行）直接跳过
        if not code and not raw_measured and not raw_required and not raw_bearing:
            continue
        kept += 1
        if not code:
            errors.append((i + 1, "灯号空白"))
            continue
        try:
            measured = float(raw_measured)
            required = float(raw_required)
            bearing = float(raw_bearing)
        except ValueError:
            errors.append((i + 1, "光强或偏角不是有效数值"))
            continue
        rows.append(
            {
                "aid_code": code,
                "measured_cd": measured,
                "required_cd": required,
                "bearing_error_deg": bearing,
            }
        )
    return rows, errors, kept


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
    # 只读账号连这张批量表都不能打开
    if not _can_write(request.user):
        return HttpResponseForbidden("仅巡检员可使用批量登记表")
    error = ""
    if request.method == "POST":
        rows, errors, total_rows = _parse_rows(request.POST)
        if total_rows < BATCH_MIN_ROWS:
            error = "批量登记至少填写两座灯"
        elif errors:
            # 任一灯光号空白或数值无效：整批不入库，写一条失败批次尝试（无新实测行）
            line_no, reason = errors[0]
            with transaction.atomic():
                attempt = BatchAttempt.objects.create(
                    ticket=None,
                    status="failed",
                    submitted_rows=total_rows,
                    failed_row=line_no,
                    fail_reason=reason,
                    created_by=request.user.username,
                )
            return render(
                request,
                "batch_result.html",
                {"attempt": attempt, "lines": [], "failed": True, "line_no": line_no, "reason": reason},
            )
        else:
            # 全部有效：逐座判定并分别入库，整批成功才签发批次票
            results = []
            with transaction.atomic():
                attempt = BatchAttempt.objects.create(
                    ticket=None,
                    status="success",
                    submitted_rows=len(rows),
                    created_by=request.user.username,
                )
                new_ids = []
                for idx, item in enumerate(rows, start=1):
                    verdict, note = judge(
                        item["measured_cd"], item["required_cd"], item["bearing_error_deg"]
                    )
                    row = Inspection.objects.create(
                        aid_code=item["aid_code"],
                        measured_cd=item["measured_cd"],
                        required_cd=item["required_cd"],
                        bearing_error_deg=item["bearing_error_deg"],
                        verdict=verdict,
                        note=note,
                        created_by=request.user.username,
                        batch=attempt,
                    )
                    new_ids.append(str(row.pk))
                    results.append({"line_no": idx, "row": row})
                attempt.ticket = _make_ticket()
                attempt.row_keys = ",".join(new_ids)
                attempt.save(update_fields=["ticket", "row_keys"])
            return render(
                request,
                "batch_result.html",
                {"attempt": attempt, "lines": results, "failed": False},
            )
    return render(request, "batch_form.html", {"error": error})


@login_required
def ticket_view(request, ticket):
    # 成功批次票：任何登录用户（含只读）均可按票号回看
    attempt = get_object_or_404(BatchAttempt, ticket=ticket, status="success")
    rows = list(attempt.inspections.all())
    rows.sort(key=lambda r: r.pk)
    return render(request, "ticket.html", {"attempt": attempt, "rows": rows})


@login_required
def tickets_view(request):
    # 已成功的批次票清单，只读账号也能看
    attempts = BatchAttempt.objects.filter(status="success")
    return render(request, "tickets.html", {"attempts": attempts})


@login_required
def failed_attempts_view(request):
    # 失败批次尝试页只对巡检员开放
    if not _can_write(request.user):
        return HttpResponseForbidden("仅巡检员可查看失败批次尝试")
    attempts = BatchAttempt.objects.filter(status="failed")
    return render(request, "failed_attempts.html", {"attempts": attempts})
