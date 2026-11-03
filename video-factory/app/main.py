"""客户运营工作流可视化平台 P1。"""
# > 执行者：codex

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import time
import uuid
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml
import anyio.to_thread
from jsonschema import Draft202012Validator, FormatChecker
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config
from .billing import BillingClient, BillingError, points
from .compliance import load_rules, scan_text
from .exporter import assert_client_safe, safe_json_response, sha256_file
from .gates import approve_gate_atomic, check_gate_atomic, confirm_point
from .orchestrator import ORDER_LABELS, Orchestrator, VISIBLE_LABELS
from .remote_execution import RemoteExecutionClient, RemoteExecutionError
from .security import create_session, csrf_matches, csrf_token, derive_secret, parse_session, password_matches
from .state_store import StateStore, canonical_json, digest_json
from .uploads import safe_child, store_upload
from .worker import DurableWorker


templates = Jinja2Templates(directory=str(config.WEB_DIR / "templates"))
NOT_FOUND_BODY = {"code": "NOT_FOUND", "message": "内容尚未就绪"}


def create_app(
    db_path: Path | None = None,
    projects_root: Path | None = None,
    *,
    reasoner: Callable[[str, Path, int], str] | None = None,
    start_worker: bool = True,
    billing_client: Any | None = None,
    execution_client: Any | None = None,
) -> FastAPI:
    configured_root_path = os.environ.get("XG_FACTORY_ROOT_PATH", "").strip()
    if configured_root_path and not configured_root_path.startswith("/"):
        raise ValueError("XG_FACTORY_ROOT_PATH 必须为空或以 / 开头")
    if any(char in configured_root_path for char in "?#"):
        raise ValueError("XG_FACTORY_ROOT_PATH 不能包含查询参数或片段")
    root_path = f"/{configured_root_path.strip('/')}" if configured_root_path.strip("/") else ""
    cookie_path = f"{root_path}/" if root_path else "/"
    app = FastAPI(title="客户运营工作流可视化平台", version="1.0.0", docs_url=None, redoc_url=None,
                  root_path=root_path)
    app.mount("/static", StaticFiles(directory=str(config.WEB_DIR / "static")), name="static")

    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        """静态资源/页面强制 no-cache，避免浏览器缓存旧版 JS/HTML"""
        response = await call_next(request)
        if request.url.path.endswith((".js", ".css", ".html")) or "/static/" in request.url.path:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response
    store = StateStore(db_path or config.database_path())
    owns_execution_client = execution_client is None
    execution = execution_client or RemoteExecutionClient(
        config.execution_base_url(),
        ssh_host=config.execution_ssh_host(),
        ssh_user=config.execution_ssh_user(),
        ssh_key=config.execution_ssh_key(),
        timeout_seconds=config.execution_timeout_seconds(),
    )
    orchestrator = Orchestrator(
        store, reasoner=reasoner, execution_client=execution
    )
    owns_billing_client = billing_client is None
    billing = billing_client or BillingClient(
        config.billing_base_url(),
        auth_token=config.billing_auth_token(),
        admin_password=config.billing_admin_password(),
        timeout_seconds=config.billing_timeout_seconds(),
    )
    root = Path(projects_root or config.projects_dir()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    worker = DurableWorker(
        store,
        orchestrator,
        config.worker_poll_seconds(),
        lease_seconds=config.worker_lease_seconds(),
        reconcile_seconds=config.worker_reconcile_seconds(),
    )
    rules = load_rules(config.CONFIG_DIR / "compliance_rules.yaml")
    industry_contract = yaml.safe_load(config.INDUSTRY_SCHEMA_PATH.read_text(encoding="utf-8"))
    submission_schema = industry_contract["submission_schema"]
    submission_validator = Draft202012Validator(submission_schema, format_checker=FormatChecker())
    enabled_industries = {
        f"{parent['code']}/{child['code']}": {
            "label": f"{parent['label']}/{child['label']}",
            "redline_profile": child.get("redline_profile", "通用"),
        }
        for parent in industry_contract["industry_taxonomy"]
        if parent.get("enabled")
        for child in parent.get("children", [])
        if child.get("enabled") and child.get("schema_ref")
    }
    @app.middleware("http")
    async def serialize_idempotent_mutations(request: Request, call_next):
        """封住多进程下 check-then-act 幂等窗口，避免重复建账/建项目/确认。"""
        key = request.headers.get("Idempotency-Key", "")
        if request.method in {"POST", "PUT", "PATCH"} and key:
            # path 已包含项目作用域；创建项目时跨会话也必须锁同一 key，
            # 否则同一客户在两台设备重放请求仍会穿透本地幂等窗口。
            lock_name = f"idempotency:{request.url.path}:{key}"
            with store.interprocess_lock(lock_name, blocking=False) as acquired:
                if not acquired:
                    return error(409, "CONFLICT", "相同请求正在处理中，请稍后重试")
                return await call_next(request)
        return await call_next(request)

    @app.on_event("startup")
    async def _start_runtime() -> None:
        anyio.to_thread.current_default_thread_limiter().total_tokens = (
            config.request_threads()
        )
        if start_worker:
            worker.start()

    @app.on_event("shutdown")
    def _stop_runtime() -> None:
        if start_worker:
            worker.stop()
        if owns_billing_client:
            billing.close()
        if owns_execution_client:
            execution.close()

    if not start_worker:
        store.reconcile_attempts()

    def error(status: int, code: str, message: str) -> JSONResponse:
        payload = {"code": code, "message": message, "request_id": secrets.token_hex(8)}
        if status >= 500 or code == "NOT_FOUND":
            safe_json_response(payload)
        return JSONResponse(payload, status_code=status)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        if exc.status_code == 404:
            return error(404, "NOT_FOUND", NOT_FOUND_BODY["message"])
        codes = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 409: "CONFLICT", 429: "RATE_LIMITED", 503: "UNAVAILABLE"}
        return error(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))

    @app.exception_handler(Exception)
    async def safe_error(_: Request, __: Exception):
        return error(500, "INTERNAL_ERROR", "处理中，我们在跟进")

    def ops_password() -> str:
        value = os.environ.get("XG_FACTORY_OPS_PASSWORD", "")
        if not value:
            raise RuntimeError("必须设置环境变量 XG_FACTORY_OPS_PASSWORD")
        return value

    @lru_cache(maxsize=2)
    def session_secret(role: str) -> bytes:
        # PBKDF2(200k) 只在每个进程首次使用该角色时执行；轮询请求只做 HMAC。
        source = ops_password() if role == "ops" else config.client_session_secret()
        return derive_secret(source + f":{role}")

    def cookie_name(role: str) -> str:
        return "internal_session" if role == "ops" else "client_session"

    def session_for(request: Request, role: str) -> tuple[dict[str, Any], bytes]:
        secret = session_secret(role)
        session = parse_session(request.cookies.get(cookie_name(role)), secret)
        if not session or session.get("role") != role:
            if role == "ops":
                raise HTTPException(404, NOT_FOUND_BODY["message"])
            raise HTTPException(401, "积分身份已失效，请重新验证")
        if role == "client" and not isinstance(session.get("customer_id"), int):
            raise HTTPException(401, "积分身份已失效，请重新验证")
        return session, secret

    def require_client(request: Request) -> tuple[dict[str, Any], bytes]:
        return session_for(request, "client")

    def require_ops(request: Request) -> tuple[dict[str, Any], bytes]:
        return session_for(request, "ops")

    def require_csrf(request: Request, supplied: str | None, role: str) -> dict[str, Any]:
        session, secret = session_for(request, role)
        if not supplied or not csrf_matches(supplied, session, secret):
            raise HTTPException(403, "页面已过期，请刷新后重试")
        return session

    def rate_limit(key: str, limit: int, window: int) -> None:
        if not store.consume_rate_limit(key, limit, window):
            raise HTTPException(429, "请求过于频繁，请稍后再试")

    def get_project_or_404(project_id: str) -> dict[str, Any]:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        return project

    def get_client_project_or_404(request: Request, project_id: str) -> dict[str, Any]:
        session, _ = require_client(request)
        if not store.project_accessible(str(session.get("account", "")), project_id):
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        return get_project_or_404(project_id)

    def billing_http_error(exc: BillingError, action: str) -> HTTPException:
        if exc.status_code == 404:
            return HTTPException(403, "客户标识无效或尚未开户，请联系管理员")
        if exc.status_code == 409 and "insufficient" in exc.detail.lower():
            return HTTPException(409, "积分不足，暂不能开始生成，请联系管理员充值")
        if exc.status_code in {401, 403} or exc.status_code >= 500:
            return HTTPException(503, f"积分服务暂不可用，{action}未执行")
        return HTTPException(409, f"积分校验未通过，{action}未执行")

    def balance_for(customer_id: int) -> dict[str, Any]:
        try:
            result = billing.balance(customer_id)
            result["balance_decimal"] = points(result.get("balance"))
            if int(result.get("customer_id", 0)) != customer_id:
                raise BillingError("积分服务客户编号不匹配")
            if int(result.get("account_id", 0)) <= 0:
                raise BillingError("积分服务账户编号无效")
            return result
        except BillingError as exc:
            raise billing_http_error(exc, "余额查询") from exc

    def balance_alert_for(customer_id: int) -> dict[str, Any]:
        try:
            result = billing.balance_with_alerts(customer_id)
            if int(result.get("customer_id", 0)) != customer_id:
                raise BillingError("积分服务客户编号不匹配")
            return result
        except BillingError as exc:
            raise billing_http_error(exc, "余额预警查询") from exc

    def project_billing_or_409(project_id: str) -> dict[str, Any]:
        row = store.project_billing(project_id)
        if not row:
            raise HTTPException(409, "项目未绑定广州积分任务，禁止继续")
        return row

    def settle_project_billing(project_id: str) -> dict[str, Any]:
        with store.interprocess_lock(
            f"billing-settle:{project_id}", blocking=True
        ) as acquired:
            if not acquired:
                raise HTTPException(503, "项目结算锁获取失败")
            row = project_billing_or_409(project_id)
            if row["status"] in {"settled", "delivered"}:
                settled = points(row.get("settled_points") or "0")
                return {
                    "status": "settled",
                    "settlement": {"actual": f"-{settled:.2f}"},
                }
            task_id = int(row["billing_task_id"])
            try:
                result = billing.settle(task_id)
            except BillingError as exc:
                store.update_project_billing(
                    project_id, "settlement_failed", last_error=exc.detail[:500]
                )
                raise billing_http_error(exc, "结算") from exc
            settlement = result.get("settlement") or {}
            actual = abs(
                points(settlement.get("actual", result.get("estimated", "0")))
            )
            store.update_project_billing(
                project_id, "settled", settled_points=f"{actual:.2f}", last_error=None
            )
            return result

    def poll_remote_production() -> None:
        # 一个远程完成事件只能由一个 Web/worker 进程下载、登记并结算。
        with store.interprocess_lock("remote-production-poller", blocking=False) as acquired:
            if not acquired:
                return
            for completed_project_id in orchestrator.poll_remote_media():
                try:
                    settle_project_billing(completed_project_id)
                except HTTPException as exc:
                    store.audit(
                        completed_project_id, "system", "system",
                        "remote_media_settlement_blocked", completed_project_id,
                        {"status_code": exc.status_code, "detail": str(exc.detail)[:500]},
                    )

    worker.set_remote_poller(poll_remote_production)

    def assert_project_settled(project_id: str) -> dict[str, Any]:
        row = project_billing_or_409(project_id)
        try:
            task = billing.task(int(row["billing_task_id"]))
        except BillingError as exc:
            raise billing_http_error(exc, "交付校验") from exc
        if task.get("status") != "settled" or not task.get("settlement"):
            raise HTTPException(409, "项目尚未完成积分扣费，禁止交付")
        settlement = task["settlement"]
        actual = abs(points(settlement.get("actual", "0")))
        store.update_project_billing(
            project_id, "settled", settled_points=f"{actual:.2f}", last_error=None
        )
        return task

    def consume_delivery_gate(project_id: str) -> None:
        row = project_billing_or_409(project_id)
        assert_project_settled(project_id)
        try:
            prepared = billing.prepare_delivery(int(row["billing_task_id"]))
            delivery_id = int(prepared["delivery_id"])
            token = str(prepared["token"])
            billing.confirm_delivery(delivery_id, token)
        except (BillingError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, BillingError):
                raise billing_http_error(exc, "交付") from exc
            raise HTTPException(503, "积分交付门禁响应无效，禁止交付") from exc
        store.update_project_billing(
            project_id, "delivered", delivery_id=delivery_id, last_error=None
        )

    def idempotency_key(value: str | None) -> str:
        if not value or not 16 <= len(value) <= 128:
            raise HTTPException(400, "Idempotency-Key 长度必须为 16-128")
        return value

    def valid_industry_payload(data: dict[str, Any]) -> None:
        if next(submission_validator.iter_errors(data), None) is not None:
            raise HTTPException(400, "内容需求表不符合所选视频类型的数据要求")
        if data["industry_path"] not in enabled_industries:
            raise HTTPException(400, "该行业当前不可提交")
        evidence_ids = [row["asset_id"] for row in data["evidence_assets"]]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise HTTPException(400, "素材编号不能重复")

        # 客户只填内容生产必需信息；客户类型不向客户提问，由本平台业务范围推理。
        # 当前入口要求商家名与地址，故归为实体店；内容类型继续作为第一分支透传。
        content_type = data["content_type"]
        data["customer_type"] = "physical_store"
        data["current_line"] = "store"

        # 这里转换成存量工作流使用的结构，
        # 明确用“未单独收集”占位，不推断库存、有效期或经营事实。
        platform = str(data.get("platform") or "抖音").strip()
        piece_format = data.get("piece_format") or "VIDEO_SHORT"
        if piece_format not in {"VIDEO_SHORT", "IMAGE_POST"} or not platform:
            raise HTTPException(400, "内容形式或平台无效")
        data["platform"] = platform
        data["piece_format"] = piece_format
        contact = {
            "channel": "other",
            "public_value": data["contact"],
            "is_public": False,
            "evidence_asset_id": None,
        }
        data["stores"] = [{
            "store_id": "store_main",
            "display_name": data["business_name"],
            "address": data["address"],
            "city": data["address"],
            "poi_ids": [],
            "public_booking_methods": [contact],
            "internal_contact": {"name": "项目联系人", "channel": data["contact"]},
            "evidence_asset_ids": evidence_ids,
        }]
        if content_type == "store_visit":
            offer = data["offer"]
            data["offers"] = [{
                "offer_id": "offer_main",
                "name": offer["name"],
                "specification": offer["specification"],
                "amount_fen": offer["amount_fen"],
                "original_amount_fen": None,
                "valid_from": "未单独收集",
                "valid_to": "未单独收集",
                "store_ids": ["store_main"],
                "inventory_rule": {"mode": "not_collected", "quantity": None},
                "restrictions": [],
                "evidence_asset_ids": evidence_ids,
            }]
            data["signature_dishes"] = [{
                "name": data["signature_item"],
                "category": enabled_industries[data["industry_path"]]["label"],
                "store_ids": ["store_main"],
                "evidence_asset_ids": evidence_ids,
            }]
            data["package_details"] = [{
                "name": offer["name"],
                "item_lines": [{"item_name": offer["specification"], "quantity": 1, "unit": "项"}],
                "amount_fen": offer["amount_fen"],
                "store_ids": ["store_main"],
                "evidence_asset_ids": evidence_ids,
            }]
            data["offer_intent"] = {"mode": "selected", "offer_ids": ["offer_main"]}
        else:
            data["offers"] = []
            data["signature_dishes"] = []
            data["package_details"] = []
            data["offer_intent"] = {"mode": "not_collected", "offer_ids": []}
        data["contacts"] = {"internal": {"name": "项目联系人", "channel": data["contact"]}, "public": []}
        authorized_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        authorization_rows = [
            {
                "type": "material_rights",
                "purpose": "同意拍摄并使用客户上传素材制作本项目内容",
                "platforms": [platform],
                "valid_from": authorized_at,
                "valid_to": "9999-12-31T23:59:59Z",
                "status": "pending",
            },
            {
                "type": "business_qualification",
                "purpose": "存量门禁兼容标识：仅代表同意拍摄经营场所，不代表提交营业执照或经营资质",
                "platforms": [platform],
                "valid_from": authorized_at,
                "valid_to": "9999-12-31T23:59:59Z",
                "status": "pending",
            },
        ]
        if data["content_authorization"].get("portrait_confirmed"):
            authorization_rows.append({
                "type": "portrait_rights",
                "person_ref": "素材内出镜人",
                "purpose": "本项目内容展示",
                "platforms": [platform],
                "valid_from": authorized_at,
                "valid_to": "9999-12-31T23:59:59Z",
                "status": "pending",
            })
        data["authorizations"] = authorization_rows

    def client_context(request: Request, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        session, secret = require_client(request)
        return {
            "csrf": csrf_token(session, secret),
            "home_url": request.url_for("projects_page").path,
            "customer_id": session["customer_id"],
            **(extra or {}),
        }

    def _prefix(path: str) -> str:
        """使用应用的唯一部署前缀生成同源绝对路径。"""
        normalized = f"/{path.lstrip('/')}"
        if root_path and (normalized == root_path or normalized.startswith(f"{root_path}/")):
            return normalized
        return f"{root_path}{normalized}"

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        try:
            require_client(request)
            return RedirectResponse(_prefix("/projects"), 303)
        except HTTPException:
            return RedirectResponse(_prefix("/access"), 303)

    @app.get("/access", response_class=HTMLResponse)
    def access_page(request: Request):
        return templates.TemplateResponse(request, "access.html", {
            "title": "积分验证", "home_url": request.url_for("access_page").path,
        })

    @app.get("/login")
    def retired_client_login():
        return RedirectResponse(_prefix("/access"), 308)

    @app.get("/ops/login", response_class=HTMLResponse)
    def ops_login_page(request: Request):
        return templates.TemplateResponse(request, "login.html", {
            "role": "ops", "title": "内部审核登录", "home_url": request.url_for("ops_login_page").path,
        })

    @app.post("/api/v1/auth/login")
    async def login(request: Request):
        data = await request.json()

        def authenticate_ops() -> JSONResponse:
            if data.get("role") != "ops":
                raise HTTPException(404, NOT_FOUND_BODY["message"])
            role = "ops"
            ip = request.client.host if request.client else "unknown"
            rate_limit(f"login:{ip}", 8, 300)
            expected = ops_password()
            account = str(data.get("account", "")).strip()
            if not account or not password_matches(str(data.get("password", "")), expected):
                raise HTTPException(401, "账号或口令不正确")
            secret = derive_secret(expected + f":{role}")
            token = create_session(secret, claims={"role": role, "account": account})
            session = parse_session(token, secret)
            response = JSONResponse({"ok": True, "next": _prefix("/ops"), "csrf": csrf_token(session, secret)})
            if cookie_path != "/":
                response.delete_cookie(cookie_name(role), path="/")
            response.set_cookie(cookie_name(role), token, httponly=True, secure=config.cookie_secure(), samesite="strict", path=cookie_path)
            return response

        return await anyio.to_thread.run_sync(authenticate_ops)

    @app.post("/api/v1/billing/access")
    async def billing_access(request: Request):
        ip = request.client.host if request.client else "unknown"
        rate_limit(f"billing-access:{ip}", 12, 300)
        data = await request.json()
        raw_id = str(data.get("customer_id", "")).strip()
        if not raw_id.isdigit() or not 1 <= len(raw_id) <= 18 or int(raw_id) <= 0:
            raise HTTPException(400, "请输入天行者分配的数值客户编号")
        customer_id = int(raw_id)
        balance = balance_for(customer_id)
        if balance["balance_decimal"] <= 0:
            raise HTTPException(403, "积分余额为0，暂不可使用，请联系管理员充值")
        secret = session_secret("client")
        token = create_session(secret, claims={
            "role": "client",
            "account": f"billing:{customer_id}",
            "customer_id": customer_id,
            "billing_account_id": int(balance["account_id"]),
        })
        session = parse_session(token, secret)
        response = JSONResponse({
            "ok": True,
            "customer_id": customer_id,
            "balance": str(balance["balance"]),
            "next": _prefix("/projects"),
            "csrf": csrf_token(session, secret),
        })
        if cookie_path != "/":
            response.delete_cookie(cookie_name("client"), path="/")
        response.set_cookie(
            cookie_name("client"), token, httponly=True,
            secure=config.cookie_secure(), samesite="strict", path=cookie_path,
        )
        return response

    @app.get("/api/v1/billing/balance")
    def billing_balance(request: Request):
        session, _ = require_client(request)
        result = balance_for(int(session["customer_id"]))
        return {"customer_id": result["customer_id"], "balance": result["balance"]}

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, x_csrf_token: str | None = Header(None)):
        require_csrf(request, x_csrf_token, "client")
        response = JSONResponse({"ok": True})
        response.delete_cookie(cookie_name("client"), path=cookie_path)
        if cookie_path != "/":
            response.delete_cookie(cookie_name("client"), path="/")
        return response

    @app.get("/api/v1/industries")
    def industries(request: Request):
        require_client(request)
        taxonomy = []
        for parent in industry_contract["industry_taxonomy"]:
            enabled_children = [child for child in parent.get("children", []) if child.get("enabled") and child.get("schema_ref")]
            if parent.get("enabled") and enabled_children:
                taxonomy.append({"code": parent["code"], "label": parent["label"], "children": enabled_children})
        return {"taxonomy": taxonomy}

    @app.get("/projects", response_class=HTMLResponse)
    def projects_page(request: Request):
        session, _ = require_client(request)
        balance = balance_alert_for(int(session["customer_id"]))
        return templates.TemplateResponse(request, "projects.html", client_context(request, {
            "projects": store.list_projects(str(session["account"])),
            "balance": balance["balance"],
            "low_balance": bool((balance.get("low_balance") or {}).get("warning")),
        }))

    @app.get("/projects/new", response_class=HTMLResponse)
    def new_project_page(request: Request):
        return templates.TemplateResponse(request, "wizard.html", client_context(request))

    @app.get("/projects/{project_id}", response_class=HTMLResponse)
    def progress_page(project_id: str, request: Request):
        project = get_client_project_or_404(request, project_id)
        return templates.TemplateResponse(request, "progress.html", client_context(request, {"project": project, "project_id": project_id}))

    @app.get("/projects/{project_id}/confirm/{confirm_id}", response_class=HTMLResponse)
    def confirm_page(project_id: str, confirm_id: str, request: Request):
        get_client_project_or_404(request, project_id)
        item = next((row for row in store.confirmations(project_id) if row["confirm_id"] == confirm_id), None)
        if not item:
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        return templates.TemplateResponse(request, "confirm.html", client_context(request, {"project_id": project_id, "item": item, "title": "内容方案" if confirm_id == "C1" else "成片"}))

    @app.get("/projects/{project_id}/delivery", response_class=HTMLResponse)
    def delivery_page(project_id: str, request: Request):
        get_client_project_or_404(request, project_id)
        return templates.TemplateResponse(request, "delivery.html", client_context(request, {"project_id": project_id}))

    @app.get("/projects/{project_id}/review-guide", response_class=HTMLResponse)
    def review_guide_page(project_id: str, request: Request):
        get_client_project_or_404(request, project_id)
        return templates.TemplateResponse(request, "review.html", {
            "project_id": project_id, "home_url": request.url_for("projects_page").path,
        })

    @app.post("/api/v1/projects")
    async def create_project(request: Request, x_csrf_token: str | None = Header(None), idempotency_key_header: str | None = Header(None, alias="Idempotency-Key")):
        session = require_csrf(request, x_csrf_token, "client")
        rate_limit(f"create:{session['account']}", 10, 3600)
        key = idempotency_key(idempotency_key_header)
        data = await request.json()
        request_hash = digest_json(data)
        try:
            cached = store.idempotency_get(f"create_project:{session['account']}", key, request_hash)
        except RuntimeError:
            raise HTTPException(409, "同一幂等键对应了不同请求")
        if cached:
            return JSONResponse(cached[1], status_code=cached[0])
        valid_industry_payload(data)
        if data["piece_format"] != "VIDEO_SHORT":
            raise HTTPException(400, "当前积分入口只支持短视频任务")
        industry = enabled_industries[data["industry_path"]]
        findings = scan_text(" ".join(data.get("selling_points", [])), industry["redline_profile"], rules)
        if not findings["passed"]:
            raise HTTPException(400, "卖点红线预检未通过")
        current_balance = balance_for(int(session["customer_id"]))["balance_decimal"]
        estimated_points = Decimal("750")
        if current_balance <= 0:
            raise HTTPException(403, "积分余额为0，暂不可使用，请联系管理员充值")
        if estimated_points > current_balance + Decimal("100"):
            raise HTTPException(409, "积分不足：短视频预计750积分，余额加100积分透支额仍不足，请联系管理员充值")
        billing_key = f"factory-video:{session['customer_id']}:{key}"
        try:
            billing_task = billing.create_video_task(int(session["billing_account_id"]), billing_key)
        except BillingError as exc:
            raise billing_http_error(exc, "项目创建") from exc
        returned_estimate = points(billing_task.get("estimated"))
        if returned_estimate != estimated_points:
            try:
                billing.cancel(int(billing_task["id"]), "platform price contract mismatch")
            except BillingError:
                pass
            raise HTTPException(503, "广州积分定价与平台契约不一致，项目未创建")
        project_id = "prj_" + uuid.uuid4().hex[:12]
        project_dir = safe_child(root, root / project_id)
        primary = data["stores"][0]
        try:
            store.create_project(
                project_id,
                primary["display_name"],
                project_dir,
                {
                    "stores": data["stores"], "offers": data["offers"], "industry_path": data["industry_path"],
                    "content_type": data["content_type"], "customer_type": data["customer_type"],
                    "current_line": data["current_line"], "name": primary["display_name"],
                },
                {"show_process": data.get("prefs", {}).get("show_process", "full")},
                offers=data["offers"],
                piece_format=data["piece_format"],
                platform=data["platform"],
            )
            store.bind_project_billing(
                project_id,
                int(session["customer_id"]),
                int(session["billing_account_id"]),
                int(billing_task["id"]),
                "video",
                f"{returned_estimate:.2f}",
                str(billing_task.get("status", "reserved")),
            )
            store.grant_project_access(str(session["account"]), project_id)
            orchestrator.initialize_project(project_id, data)
        except Exception:
            try:
                billing.cancel(int(billing_task["id"]), "platform project initialization failed")
                if store.project_billing(project_id):
                    store.update_project_billing(project_id, "cancelled")
            except (BillingError, KeyError):
                pass
            raise
        response = {
            "project_id": project_id,
            "piece_id": f"piece_{project_id}",
            "stage": "资料建档",
            "estimated_points": f"{returned_estimate:.2f}",
            "redline_preview": findings,
        }
        store.idempotency_put(f"create_project:{session['account']}", key, request_hash, 201, response)
        return JSONResponse(response, status_code=201)

    @app.get("/api/v1/projects")
    def list_projects(request: Request):
        session, _ = require_client(request)
        return {"items": [{"project_id": row["id"], "status": row["status"], "created_at": row["created_at"]} for row in store.list_projects(str(session["account"]))]}

    @app.post("/api/v1/redline-preview")
    async def redline_preview(request: Request):
        require_client(request)
        data = await request.json()
        profile = enabled_industries.get(str(data.get("industry_path", "")), {}).get("redline_profile", "通用")
        return scan_text(str(data.get("text", "")), profile, rules)

    @app.post("/api/v1/projects/{project_id}/assets")
    async def upload_asset(
        project_id: str,
        request: Request,
        file: UploadFile = File(...),
        store_id: str = Form(...),
        planned_asset_id: str | None = Form(None),
        evidence_type: str | None = Form(None),
        x_csrf_token: str | None = Header(None),
        idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
    ):
        require_csrf(request, x_csrf_token, "client")
        idempotency_key(idempotency_key_header)
        project = get_client_project_or_404(request, project_id)
        if store_id not in {row["store_id"] for row in project["stores"]}:
            raise HTTPException(400, "素材绑定门店不存在")
        if planned_asset_id or evidence_type:
            brief = json.loads((Path(project["project_dir"]) / "BRIEF.json").read_text(encoding="utf-8"))
            planned = next((row for row in brief.get("evidence_assets", []) if row["asset_id"] == planned_asset_id), None)
            if not planned or planned["evidence_type"] != evidence_type or planned["store_id"] != store_id:
                raise HTTPException(400, "素材证据绑定与需求表不一致")
            if any(row["planned_asset_id"] == planned_asset_id for row in store.evidence_bindings(project_id)):
                raise HTTPException(409, "该证据素材已经上传")
        data = await file.read(20 * 1024 * 1024 + 1)
        existing_assets = store.assets(project_id)
        if len(existing_assets) >= 40:
            raise HTTPException(400, "单个项目最多上传 40 个素材")
        if sum(row["bytes"] for row in existing_assets) + len(data) > 200 * 1024 * 1024:
            raise HTTPException(400, "单个项目素材总量不得超过 200MB")
        request_hash = hashlib.sha256(data + f"{store_id}|{planned_asset_id}|{evidence_type}".encode()).hexdigest()
        try:
            cached = store.idempotency_get(f"asset:{project_id}", idempotency_key_header, request_hash)
        except RuntimeError:
            raise HTTPException(409, "同一幂等键对应了不同素材")
        if cached:
            return JSONResponse(cached[1], status_code=cached[0])
        try:
            path, mime, digest = store_upload(Path(project["project_dir"]), file.filename or "素材", file.content_type or "", data)
        except (ValueError, json.JSONDecodeError, subprocess.SubprocessError):
            raise HTTPException(400, "素材格式、大小、像素、时长或帧率不符合要求")
        try:
            asset_id = store.add_asset(project_id, file.filename or "素材", path.name, mime, path.stat().st_size, digest, store_id)
            if planned_asset_id and evidence_type:
                store.bind_asset_evidence(project_id, planned_asset_id, asset_id, evidence_type)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        response = {"asset_id": asset_id, "stored_name": path.name}
        store.idempotency_put(f"asset:{project_id}", idempotency_key_header, request_hash, 201, response)
        orchestrator.export_ready_views(project_id)
        return JSONResponse(response, status_code=201)

    @app.get("/api/v1/projects/{project_id}/assets")
    def list_assets(project_id: str, request: Request):
        require_client(request)
        get_client_project_or_404(request, project_id)
        return {"items": [{key: value for key, value in row.items() if key not in {"relative_path", "stored_name", "sha256", "project_id"}} for row in store.assets(project_id)]}

    @app.delete("/api/v1/projects/{project_id}/assets/{asset_id}")
    def delete_asset(project_id: str, asset_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        require_csrf(request, x_csrf_token, "client")
        project = get_client_project_or_404(request, project_id)
        item = next((row for row in store.assets(project_id) if row["id"] == asset_id), None)
        if not item:
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        if item["used_in"]:
            raise HTTPException(409, "素材已用于产出物，请先走影响分析")
        removed = store.remove_asset(project_id, asset_id)
        path = safe_child(Path(project["project_dir"]), Path(project["project_dir"]) / removed["relative_path"])
        path.unlink(missing_ok=True)
        store.invalidate_confirmations(project_id, ["C1", "C2"], "素材删除")
        return {"ok": True}

    @app.get("/api/v1/projects/{project_id}/progress")
    def progress(project_id: str, request: Request, if_none_match: str | None = Header(None)):
        session, _ = require_client(request)
        rate_limit(f"progress:{session['account']}:{project_id}", 120, 60)
        get_client_project_or_404(request, project_id)
        result = orchestrator.progress(project_id)
        safe_json_response(result)
        etag = '"' + hashlib.sha256(canonical_json(result).encode()).hexdigest() + '"'
        if if_none_match == etag:
            return Response(status_code=304)
        return JSONResponse(result, headers={"ETag": etag, "Cache-Control": "private, no-cache"})

    @app.get("/api/v1/projects/{project_id}/artifacts")
    def artifacts(project_id: str, request: Request):
        require_client(request)
        project = get_client_project_or_404(request, project_id)
        if project["prefs"].get("show_process") == "result_only":
            return {"items": []}
        items = []
        for row in store.artifacts(project_id, client_only=True):
            stage_key = orchestrator.catalog["views"][row["client_view_id"]]["stage"]
            items.append({
                "client_view_id": row["client_view_id"],
                "label": VISIBLE_LABELS.get(row["client_view_id"], "专业产出"),
                "stage": orchestrator.stage_labels.get(stage_key, {"label": "项目进度"})["label"],
                "updated_at": row["exported_at"],
            })
        result = {"items": items}
        safe_json_response(result)
        return result

    @app.get("/api/v1/projects/{project_id}/artifacts/{view_id}")
    def artifact_detail(project_id: str, view_id: str, request: Request):
        require_client(request)
        project = get_client_project_or_404(request, project_id)
        if project["prefs"].get("show_process") == "result_only":
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        item = store.artifact(project_id, view_id, formal_only=True)
        if not item or not view_id.startswith("D_"):
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        path = safe_child(Path(project["project_dir"]), Path(item["path"]))
        rendered = path.read_text(encoding="utf-8")
        assert_client_safe(rendered)
        result: dict[str, Any] = {"label": VISIBLE_LABELS.get(view_id, "专业产出"), "rendered_html": rendered, "updated_at": item["exported_at"]}
        if view_id == "D_CYCLE_MEDIA":
            video = store.artifact(project_id, "A_VIDEO_MASTER", formal_only=True)
            if video:
                token = secrets.token_urlsafe(32)
                low_preview = Path(project["project_dir"]) / "previews" / "C2_low.mp4"
                selected = low_preview if low_preview.is_file() else Path(video["path"])
                relative = str(selected.resolve().relative_to(Path(project["project_dir"]).resolve()))
                store.save_download_token(token, project_id, relative, "preview", 900, video["id"])
                result["media_url"] = _prefix(f"/api/v1/projects/{project_id}/media/{token}")
        safe_json_response(result)
        return result

    @app.get("/api/v1/projects/{project_id}/media/{token}")
    def media_preview(project_id: str, token: str, request: Request):
        require_client(request)
        project = get_client_project_or_404(request, project_id)
        row = store.resolve_download_token(token, project_id)
        if not row or row["kind"] != "preview":
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        path = safe_child(Path(project["project_dir"]), Path(project["project_dir"]) / row["relative_path"])
        return FileResponse(path, media_type="video/mp4", filename="成片预览.mp4")

    @app.get("/api/v1/projects/{project_id}/confirmations")
    def confirmations(project_id: str, request: Request):
        require_client(request)
        get_client_project_or_404(request, project_id)
        items = []
        for row in store.confirmations(project_id):
            items.append({
                "confirm_id": row["confirm_id"], "title": "内容方案" if row["confirm_id"] == "C1" else "成片",
                "revision": row["revision"], "decision": row["decision"],
                "payload_view_ids": ["D_CYCLE_TOPICS", "D_CYCLE_COPY_SET"] if row["confirm_id"] == "C1" else ["D_CYCLE_MEDIA", "D_CYCLE_PLATFORM_COPY"],
                "scope_statement": "确认内容方向、门店事实与表达习惯；不覆盖商业效果。",
            })
        return {"items": items}

    @app.post("/api/v1/projects/{project_id}/confirmations/{confirm_id}")
    async def decide_confirmation(
        project_id: str,
        confirm_id: str,
        request: Request,
        x_csrf_token: str | None = Header(None),
        idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
    ):
        session = require_csrf(request, x_csrf_token, "client")
        key = idempotency_key(idempotency_key_header)
        project = get_client_project_or_404(request, project_id)
        data = await request.json()
        allowed = {"decision", "revision", "revise_scope", "note", "attribution"}
        if set(data) - allowed:
            raise HTTPException(400, "确认请求包含未允许字段")
        decision = data.get("decision")
        if decision not in {"ok", "revise", "pause"} or not isinstance(data.get("revision"), int):
            raise HTTPException(400, "确认决定或版本无效")
        if decision == "revise" and (not data.get("revise_scope") or not str(data.get("note", "")).strip()):
            raise HTTPException(400, "修改时必须选择范围并填写说明")
        request_hash = digest_json(data)
        try:
            cached = store.idempotency_get(f"confirm:{project_id}:{confirm_id}", key, request_hash)
        except RuntimeError:
            raise HTTPException(409, "同一幂等键对应了不同确认")
        if cached:
            return cached[1]
        if decision == "ok" and confirm_id == "C1":
            rc, output = confirm_point(Path(project["project_dir"]), "node4_copy", "可以")
            if rc != 0:
                raise HTTPException(409, "确认兼容检查未通过")
        try:
            store.decide_confirmation(
                project_id, confirm_id, project["piece"]["id"], decision,
                note=str(data.get("note", "")), revise_scope=data.get("revise_scope"), actor_type="client",
                revision=data["revision"], attribution=data.get("attribution"), actor=session.get("account", "client"),
            )
        except RuntimeError:
            raise HTTPException(409, "确认版本已变化，请刷新后重试")
        if decision == "revise":
            scope_map = {"topic": "topic_change", "copy": "copy_small_change", "typo": "typo_only", "shot": "shot_only_change", "technical": "tech_issue"}
            orchestrator.rollback(project_id, scope_map.get(data["revise_scope"], "copy_small_change"), data.get("attribution") or "client_taste_change")
            next_text = "修改已登记，系统只回退受影响部分"
        elif decision == "pause":
            run = next((row for row in store.node_runs(project_id) if row["node_id"] in {"COPY_PACKAGE", "MEDIA_PRODUCTION"} and row["status"] == "CLIENT_CONFIRM"), None)
            if run:
                store.set_node(project_id, run["node_id"], run["cycle_id"], run["piece_id"], "PAUSED_BY_CLIENT")
            next_text = "已暂停，负责人会联系你"
        else:
            next_text = orchestrator.advance(project_id)
            worker.wake()
        response = {"ok": True, "next": next_text}
        store.idempotency_put(f"confirm:{project_id}:{confirm_id}", key, request_hash, 200, response)
        return response

    @app.patch("/api/v1/projects/{project_id}/preferences")
    async def preferences(project_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        require_csrf(request, x_csrf_token, "client")
        get_client_project_or_404(request, project_id)
        data = await request.json()
        if set(data) != {"show_process"} or data["show_process"] not in {"full", "result_only"}:
            raise HTTPException(400, "展示偏好无效")
        return {"ok": True, "prefs": store.update_preferences(project_id, data)}

    @app.get("/api/v1/projects/{project_id}/order")
    def get_order(project_id: str, request: Request):
        require_client(request)
        get_client_project_or_404(request, project_id)
        row = store.order(project_id)
        return {"quote_version": row["quote_version"], "scope": row["scope"], "revise_quota_left": row["revise_quota_left"], "status": ORDER_LABELS.get(row["status"], "未登记")}

    @app.get("/api/v1/projects/{project_id}/delivery")
    def delivery(project_id: str, request: Request):
        require_client(request)
        project = get_client_project_or_404(request, project_id)
        if not store.gate_allowed(project_id, "G_DELIVERY_READY"):
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        assert_project_settled(project_id)
        target = Path(project["project_dir"]) / "delivery" / f"{project_id}_交付资料包.zip"
        if not target.is_file():
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        token = secrets.token_urlsafe(32)
        relative = str(target.resolve().relative_to(Path(project["project_dir"]).resolve()))
        store.save_download_token(token, project_id, relative, "bundle", 900)
        result = {"items": [{
            "kind": "package",
            "label": "交付资料包",
            "size": target.stat().st_size,
            "download_token": token,
            "download_url": _prefix(f"/api/v1/projects/{project_id}/delivery/{token}"),
            "preview_only": False,
        }], "review_guide_view_id": "review-guide"}
        safe_json_response(result)
        return result

    @app.get("/api/v1/projects/{project_id}/delivery/{token}")
    def download(project_id: str, token: str, request: Request):
        require_client(request)
        rate_limit(f"download:{project_id}", 20, 60)
        project = get_client_project_or_404(request, project_id)
        row = store.resolve_download_token(token, project_id)
        if not row or row["kind"] != "bundle":
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        path = safe_child(Path(project["project_dir"]), Path(project["project_dir"]) / row["relative_path"])
        consume_delivery_gate(project_id)
        return FileResponse(path, media_type="application/zip", filename="交付资料包.zip")

    @app.get("/api/v1/projects/{project_id}/review-reminders")
    def reminders(project_id: str, request: Request):
        require_client(request)
        get_client_project_or_404(request, project_id)
        return {"items": [
            {"at": "T+1 天", "what": "播放、完播、前三秒流失", "why": "判断开头是否抓人", "action": "开头弱就先换开头重剪；是否有效需下一轮数据验证"},
            {"at": "T+3 天", "what": "赞评藏、主页访问", "why": "判断内容有没有共鸣", "action": "互动弱就调整选题；是否有效需下一轮数据验证"},
            {"at": "T+7 天", "what": "咨询、到店提及、成交", "why": "判断承接是否有效", "action": "有播放没咨询就检查门店位置和预约入口；是否有效需下一轮数据验证"},
        ]}

    @app.get("/ops", response_class=HTMLResponse)
    def ops_page(request: Request):
        session, secret = require_ops(request)
        pending = []
        for project in store.list_projects():
            for run in store.node_runs(project["id"]):
                if run["status"] in {"INTERNAL_REVIEW", "WAITING_BOSS_APPROVAL"}:
                    gate = orchestrator.registry["nodes"][run["node_id"]]["exit_gate"]
                    pending.append({"project_id": project["id"], "node_id": run["node_id"], "gate_id": gate, "status": run["status"]})
        return templates.TemplateResponse(request, "ops.html", {"pending": pending, "projects": store.list_projects(), "csrf": csrf_token(session, secret), "home_url": request.url_for("ops_page").path, "paid_enabled": config.PAID_API_ENABLED, "auto_publish": config.AUTO_PUBLISH_ENABLED, "daily": store.daily_metrics(root)})

    @app.get("/internal/v1/reviews/pending")
    def internal_pending(request: Request):
        require_ops(request)
        items = []
        for project in store.list_projects():
            for run in store.node_runs(project["id"]):
                if run["status"] != "INTERNAL_REVIEW":
                    continue
                node = orchestrator.registry["nodes"][run["node_id"]]
                produces = [row for row in store.artifacts(project["id"]) if row["artifact_id"] in node["produces"] and not row["mock"]]
                items.append({
                    "project_id": project["id"], "gate_id": node["exit_gate"], "status": run["status"],
                    "evidence_artifact_id": produces[0]["artifact_id"] if produces else None,
                    "basis_preview": [{"artifact_id": row["artifact_id"], "sha256": row["sha256"], "bytes": row["bytes"]} for row in produces],
                })
        return {"items": items}

    @app.post("/internal/v1/projects/{project_id}/gates/{gate_id}/check")
    def internal_check(project_id: str, gate_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        require_csrf(request, x_csrf_token, "ops")
        get_project_or_404(project_id)
        result = check_gate_atomic(store, project_id, orchestrator.registry, gate_id, derive_secret(ops_password() + ":gate-token"))
        return result

    @app.post("/internal/v1/projects/{project_id}/gates/{gate_id}/approve")
    async def internal_approve(project_id: str, gate_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        data = await request.json()

        def approve() -> dict[str, Any]:
            session = require_csrf(request, x_csrf_token, "ops")
            project = get_project_or_404(project_id)
            if set(data) - {"check_token", "evidence_artifact_id", "cycle", "piece"}:
                raise HTTPException(400, "审批身份与文件路径只能由服务端解析")
            if not data.get("check_token") or not str(data.get("evidence_artifact_id", "")).startswith("A_"):
                raise HTTPException(400, "审批令牌与证据产物不能为空")
            if gate_id == "G_DELIVERY_READY":
                assert_project_settled(project_id)
            result = approve_gate_atomic(store, project_id, orchestrator.registry, gate_id, data["check_token"], data["evidence_artifact_id"], session.get("account", "operator"))
            if gate_id == "G_PROJECT_AUTHORIZED":
                store.verify_authorizations(project_id, session.get("account", "operator"))
            if result["rc"] == 0:
                node_id = next(node_id for node_id, node in orchestrator.registry["nodes"].items() if node["exit_gate"] == gate_id)
                run = next((row for row in store.node_runs(project_id) if row["node_id"] == node_id), None)
                store.set_node(project_id, node_id, None if node_id == "PROJECT_CHARTER" else project["cycle"]["id"], None if node_id == "PROJECT_CHARTER" else project["piece"]["id"], "SIGNED_OFF" if node_id == "PROJECT_CHARTER" else "PRODUCED")
                if gate_id == "G_DELIVERY_READY":
                    store.set_node(project_id, node_id, run["cycle_id"] if run else project["cycle"]["id"], run["piece_id"] if run else project["piece"]["id"], "SIGNED_OFF")
                    orchestrator.prepare_delivery(project_id)
            return result

        return await anyio.to_thread.run_sync(approve)

    @app.post("/internal/v1/projects/{project_id}/advance")
    def internal_advance(project_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        require_csrf(request, x_csrf_token, "ops")
        get_project_or_404(project_id)
        status = orchestrator.advance(project_id)
        worker.wake()
        return {"ok": True, "status": status}

    @app.post("/internal/v1/projects/{project_id}/nodes/{node_id}/run")
    async def run_node(project_id: str, node_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        data = await request.json()

        def enqueue() -> JSONResponse:
            require_csrf(request, x_csrf_token, "ops")
            project = get_project_or_404(project_id)
            if node_id not in orchestrator.registry["nodes"]:
                raise HTTPException(404, NOT_FOUND_BODY["message"])
            attempt_id = store.enqueue_node(project_id, node_id, project["cycle"]["id"], project["piece"]["id"], data)
            worker.wake()
            return JSONResponse({"ok": True, "attempt_id": attempt_id}, status_code=202)

        return await anyio.to_thread.run_sync(enqueue)

    @app.post("/internal/v1/projects/{project_id}/nodes/{node_id}/retry")
    async def retry_node(project_id: str, node_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        return await run_node(project_id, node_id, request, x_csrf_token)

    @app.post("/internal/v1/projects/{project_id}/rollback")
    async def rollback(project_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        data = await request.json()

        def apply_rollback() -> JSONResponse:
            require_csrf(request, x_csrf_token, "ops")
            get_project_or_404(project_id)
            target = orchestrator.rollback(project_id, data.get("error_type", ""), data.get("attribution", ""))
            return JSONResponse({"ok": True, "target": target}, status_code=202)

        return await anyio.to_thread.run_sync(apply_rollback)

    @app.post("/internal/v1/projects/{project_id}/confirm-points/{point}/confirm")
    async def internal_confirm(project_id: str, point: str, request: Request, x_csrf_token: str | None = Header(None)):
        data = await request.json()

        def confirm() -> dict[str, Any]:
            require_csrf(request, x_csrf_token, "ops")
            project = get_project_or_404(project_id)
            if data.get("quote") not in {None, "可以"}:
                raise HTTPException(400, "确认适配器只接受规范枚举")
            rc, output = confirm_point(Path(project["project_dir"]), point, "可以")
            return {"rc": rc, "output": output}

        return await anyio.to_thread.run_sync(confirm)

    @app.post("/internal/v1/projects/{project_id}/confirm-points/{point}/revoke")
    def internal_revoke(project_id: str, point: str, request: Request, x_csrf_token: str | None = Header(None)):
        require_csrf(request, x_csrf_token, "ops")
        get_project_or_404(project_id)
        mapping = {"node4_copy": ["C1", "C2"], "node8_image": ["C2"], "node12_render": ["C2"]}
        if point not in mapping:
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        count = store.invalidate_confirmations(project_id, mapping[point], "内部作废")
        return {"ok": True, "invalidated": count}

    @app.post("/internal/v1/projects/{project_id}/insights/import")
    async def import_insights(project_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        data = await request.json()

        def import_items() -> dict[str, Any]:
            session = require_csrf(request, x_csrf_token, "ops")
            get_project_or_404(project_id)
            count = orchestrator.import_insights(project_id, data.get("items", []), session.get("account", "operator"))
            return {"ok": True, "imported": count}

        return await anyio.to_thread.run_sync(import_items)

    @app.post("/internal/v1/projects/{project_id}/media/compose")
    async def compose_media(project_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        data = await request.json()

        def compose() -> dict[str, Any]:
            require_csrf(request, x_csrf_token, "ops")
            get_project_or_404(project_id)
            if config.PAID_API_ENABLED:
                raise HTTPException(409, "广州业务节点禁止本机合成，请使用新加坡生产通道")
            path = orchestrator.compose_media(project_id, str(data.get("asset_id", "")))
            settlement = settle_project_billing(project_id)
            return {
                "ok": True,
                "sha256": sha256_file(path),
                "technical_check": "passed",
                "billing_status": settlement["status"],
                "charged_points": abs(points((settlement.get("settlement") or {}).get("actual", "0"))),
            }

        return await anyio.to_thread.run_sync(compose)

    @app.post("/internal/v1/projects/{project_id}/media/execute")
    def execute_remote_media(
        project_id: str,
        request: Request,
        x_csrf_token: str | None = Header(None),
    ):
        session = require_csrf(request, x_csrf_token, "ops")
        project = get_project_or_404(project_id)
        if not config.PAID_API_ENABLED:
            raise HTTPException(503, "付费生成总开关未开启")
        c1 = next(
            (item for item in store.confirmations(project_id) if item["confirm_id"] == "C1"),
            None,
        )
        if not c1 or c1["status"] != "ok":
            raise HTTPException(409, "内容方案尚未获客户确认，禁止生成")
        if not store.gate_allowed(project_id, "G_RENDER_READY"):
            raise HTTPException(409, "素材与制作准备门尚未通过")
        authorizations = store.authorizations(project_id)
        if not authorizations or any(row["status"] != "verified" for row in authorizations):
            raise HTTPException(409, "素材授权尚未完成内部核验")
        billing_row = project_billing_or_409(project_id)
        if billing_row["status"] in {"settled", "delivered"}:
            raise HTTPException(409, "该项目已完成积分结算，不得重复生成")
        with store.interprocess_lock(f"remote-submit:{project_id}", blocking=False) as acquired:
            if not acquired:
                raise HTTPException(409, "该项目的远程生成请求正在提交")
            try:
                job = orchestrator.submit_remote_media(project_id)
            except RemoteExecutionError as exc:
                raise HTTPException(503, str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(409, str(exc)) from exc
        store.audit(
            project_id, session.get("account", "operator"), "internal_ops",
            "paid_remote_generation_authorized", job["remote_job_id"],
            {"request_hash": job["request_hash"], "content_type": json.loads((Path(project["project_dir"]) / "BRIEF.json").read_text(encoding="utf-8"))["content_type"]},
        )
        worker.wake()
        return JSONResponse({
            "ok": True,
            "status": job["status"],
            "remote_job_id": job["remote_job_id"],
        }, status_code=202)

    @app.get("/internal/v1/projects/{project_id}/media/execute/status")
    def remote_media_status(project_id: str, request: Request):
        require_ops(request)
        get_project_or_404(project_id)
        worker.wake_remote()
        row = store.remote_production_job(project_id)
        if not row:
            raise HTTPException(404, NOT_FOUND_BODY["message"])
        return {
            "status": row["status"],
            "remote_job_id": row["remote_job_id"],
            "error": row["error"],
            "updated_at": row["updated_at"],
        }

    @app.post("/internal/v1/projects/{project_id}/paid-steps/{step_id}/authorize")
    async def paid_authorize(project_id: str, step_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        data = await request.json()

        def review_authorization() -> dict[str, Any]:
            session = require_csrf(request, x_csrf_token, "ops")
            get_project_or_404(project_id)
            order = store.order(project_id)
            states = {
                "paid_api_enabled": config.PAID_API_ENABLED,
                "single_order_authorized": bool(data.get("request_hash")),
                "request_hash_matches": False,
                "estimated_cap_ok": False,
                "payment_cleared": order["status"] in {"deposit_paid", "fully_paid", "internal_test_exempt"},
            }
            store.audit(project_id, session.get("account", "operator"), "internal_ops", "paid_authorization_reviewed", step_id, states)
            return {"ok": False, "status": "WAITING_BOSS_APPROVAL", "conditions": states}

        return await anyio.to_thread.run_sync(review_authorization)

    @app.get("/internal/v1/projects/{project_id}/order")
    def internal_get_order(project_id: str, request: Request):
        require_ops(request)
        get_project_or_404(project_id)
        return store.order(project_id)

    @app.post("/internal/v1/projects/{project_id}/order")
    async def internal_update_order(project_id: str, request: Request, x_csrf_token: str | None = Header(None)):
        data = await request.json()

        def update_order() -> dict[str, Any]:
            session = require_csrf(request, x_csrf_token, "ops")
            get_project_or_404(project_id)
            return store.update_order(project_id, data.get("status", ""), session.get("account", "operator"), data.get("payment_evidence_ref"))

        return await anyio.to_thread.run_sync(update_order)

    @app.get("/internal/v1/projects/{project_id}/audit")
    def internal_audit(project_id: str, request: Request):
        require_ops(request)
        get_project_or_404(project_id)
        return {"items": store.audit_events(project_id), "hash_chain_ok": store.verify_audit(project_id)}

    @app.get("/internal/v1/ops/daily-check")
    def daily_check(request: Request):
        require_ops(request)
        return store.daily_metrics(root)

    @app.post("/internal/v1/admin/reindex")
    def reindex(request: Request, x_csrf_token: str | None = Header(None)):
        require_csrf(request, x_csrf_token, "ops")
        count = 0
        for project in store.list_projects():
            project_dir = Path(project["project_dir"])
            for artifact_id, spec in orchestrator.registry["artifacts"].items():
                path = project_dir / spec["path"]
                if path.is_file() and path.stat().st_size > 0:
                    store.add_artifact(project["id"], artifact_id, path, sha256_file(path), None, project["cycle"]["id"], project["piece"]["id"], "_MOCK" in path.name)
                    count += 1
            orchestrator.export_ready_views(project["id"])
        return JSONResponse({"ok": True, "indexed": count}, status_code=202)

    app.state.store = store
    app.state.orchestrator = orchestrator
    app.state.billing = billing
    app.state.execution = execution
    app.state.worker = worker
    app.state.projects_root = root
    app.state.root_path = root_path
    app.state.cookie_path = cookie_path
    return app


app = create_app()
