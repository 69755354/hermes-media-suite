"""广州积分服务客户端；广州账本是唯一事实源。"""
# > 执行者：codex

from __future__ import annotations

import copy
import threading
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx


class BillingError(RuntimeError):
    """积分服务返回拒绝或当前不可达。"""

    def __init__(self, message: str, *, status_code: int = 502, detail: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or message


def points(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BillingError("积分服务返回了无效积分数", detail=str(value)) from exc
    if not result.is_finite():
        raise BillingError("积分服务返回了无效积分数", detail=str(value))
    return result


class BillingClient:
    """只封装平台实际需要的查询、任务、结算和交付门禁接口。"""

    def __init__(
        self,
        base_url: str,
        *,
        auth_token: str = "",
        admin_password: str = "",
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._auth_token = auth_token.strip()
        self._admin_password = admin_password
        self._token_lock = threading.Lock()
        self._settle_lock = threading.RLock()
        self._settled_tasks: dict[int, dict[str, Any]] = {}
        self._timeout = httpx.Timeout(timeout_seconds)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self._timeout,
            transport=transport,
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )

    def close(self) -> None:
        self._client.close()

    def _login(self) -> str:
        if not self._admin_password:
            raise BillingError(
                "积分服务认证未配置",
                status_code=503,
                detail="缺少 XG_FACTORY_BILLING_AUTH_TOKEN 或 XG_FACTORY_BILLING_ADMIN_PASSWORD",
            )
        with self._token_lock:
            if self._auth_token:
                return self._auth_token
            try:
                response = self._client.post(
                    "/auth/admin-login",
                    json={"password": self._admin_password},
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                raise BillingError("积分服务暂不可用", status_code=503, detail=str(exc)) from exc
            if response.status_code != 200:
                raise BillingError(
                    "积分服务认证失败",
                    status_code=503,
                    detail=self._response_detail(response),
                )
            token = str(response.json().get("token", "")).strip()
            if not token:
                raise BillingError("积分服务认证响应缺少 token", status_code=503)
            self._auth_token = token
            return token

    @staticmethod
    def _response_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text[:500]
        if isinstance(body, dict):
            return str(body.get("detail") or body.get("message") or body)[:500]
        return str(body)[:500]

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self._auth_token or self._login()
        for attempt in range(2):
            try:
                response = self._client.request(
                    method,
                    path,
                    json=json,
                    headers={"X-Auth-Token": token},
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                raise BillingError("积分服务暂不可用", status_code=503, detail=str(exc)) from exc
            if response.status_code == 401 and attempt == 0 and self._admin_password:
                # 仅让仍持有失效 token 的线程清空缓存；避免另一个线程刚刷新成功
                # 又被本线程覆盖。扣费请求本身不使用进程内全局锁串行化。
                with self._token_lock:
                    if self._auth_token == token:
                        self._auth_token = ""
                token = self._login()
                continue
            if response.status_code >= 400:
                raise BillingError(
                    "积分服务拒绝请求",
                    status_code=response.status_code,
                    detail=self._response_detail(response),
                )
            try:
                body = response.json()
            except ValueError as exc:
                raise BillingError("积分服务返回了无效 JSON", detail=response.text[:500]) from exc
            if not isinstance(body, dict):
                raise BillingError("积分服务响应格式无效", detail=str(body)[:500])
            return body
        raise BillingError("积分服务认证失败", status_code=503)

    def balance(self, customer_id: int) -> dict[str, Any]:
        return self._request("GET", f"/customers/{customer_id}/balance")

    def balance_with_alerts(self, customer_id: int) -> dict[str, Any]:
        return self._request("GET", f"/customers/{customer_id}/balance/m4")

    def create_video_task(self, account_id: int, idempotency_key: str) -> dict[str, Any]:
        # strategy 不在平台重复提交；广州服务端对 video 自动绑定 strategy×1。
        return self._request(
            "POST",
            "/tasks",
            json={
                "account_id": account_id,
                "task_type": "video",
                "items": [{"item_type": "video", "quantity": 1}],
                "idempotency_key": idempotency_key,
            },
        )

    def task(self, task_id: int) -> dict[str, Any]:
        return self._request("GET", f"/tasks/{task_id}")

    def settle(self, task_id: int) -> dict[str, Any]:
        # 同一进程先走成功结果缓存；首次结算也先读广州账本状态。
        # 项目层另有跨进程文件锁，二者共同避免重复 POST 扣费。
        with self._settle_lock:
            cached = self._settled_tasks.get(task_id)
            if cached is not None:
                return copy.deepcopy(cached)
            current = self.task(task_id)
            if current.get("status") == "settled":
                self._settled_tasks[task_id] = copy.deepcopy(current)
                return current
            result = self._request(
                "POST",
                f"/tasks/{task_id}/settle",
                json={"reason": f"ai-video-factory generation completed: task {task_id}"},
            )
            if result.get("status") == "settled" or result.get("settlement"):
                self._settled_tasks[task_id] = copy.deepcopy(result)
            return result

    def cancel(self, task_id: int, reason: str) -> dict[str, Any]:
        return self._request(
            "POST", f"/tasks/{task_id}/cancel", json={"reason": reason[:1000]}
        )

    def prepare_delivery(self, task_id: int) -> dict[str, Any]:
        return self._request("POST", "/deliveries/prepare", json={"task_id": task_id})

    def confirm_delivery(self, delivery_id: int, token: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/deliveries/confirm",
            json={"delivery_id": delivery_id, "token": token},
        )
