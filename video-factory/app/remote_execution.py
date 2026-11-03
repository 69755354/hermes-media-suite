"""广州到新加坡媒体生产通道；HTTP 走 SSH 隧道，素材和结果走 SCP。"""
# > 执行者：codex

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import httpx


class RemoteExecutionError(RuntimeError):
    pass


class RemoteExecutionClient:
    """封装 Execute API 持久任务及跨机文件传输。"""

    _SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
    _SAFE_RESULT = re.compile(
        r"^/home/ubuntu/\.hermes/profiles/customer/cache/[A-Za-z0-9_-]+_final\.mp4$"
    )

    def __init__(
        self,
        base_url: str,
        *,
        ssh_host: str,
        ssh_user: str,
        ssh_key: Path,
        timeout_seconds: float = 20,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_key = Path(ssh_key)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            transport=transport,
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )

    def close(self) -> None:
        self._client.close()

    def _json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, json=payload)
        except httpx.HTTPError as exc:
            raise RemoteExecutionError(f"新加坡执行通道不可达：{exc}") from exc
        if response.status_code >= 400:
            raise RemoteExecutionError(f"新加坡执行通道返回 HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise RemoteExecutionError("新加坡执行通道返回无效 JSON") from exc
        if not isinstance(body, dict):
            raise RemoteExecutionError("新加坡执行通道响应格式无效")
        return body

    def ping(self) -> bool:
        return self._json("POST", "/ping", {}).get("status") == "alive"

    def _ssh_base(self) -> list[str]:
        if not self.ssh_key.is_file():
            raise RemoteExecutionError("新加坡 SSH 密钥不存在")
        return [
            "-i", str(self.ssh_key), "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=yes",
        ]

    def submit(
        self,
        project_id: str,
        script: str,
        assets: list[Path],
        *,
        content_type: str,
    ) -> str:
        if not self._SAFE_ID.fullmatch(project_id):
            raise RemoteExecutionError("项目编号不符合跨机传输规则")
        if content_type not in {"store_visit", "drama"}:
            raise RemoteExecutionError("口播必须走婵镜通道，禁止误投 Seedance Execute API")
        remote_dir = f"/tmp/factory-platform/{project_id}/assets"
        ssh_target = f"{self.ssh_user}@{self.ssh_host}"
        mkdir = subprocess.run(
            ["ssh", *self._ssh_base(), ssh_target, "mkdir", "-p", remote_dir],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if mkdir.returncode != 0:
            raise RemoteExecutionError((mkdir.stderr or "新加坡素材目录创建失败")[-500:])
        remote_assets: list[str] = []
        for index, asset in enumerate(assets, 1):
            path = Path(asset).resolve()
            if not path.is_file():
                raise RemoteExecutionError(f"待传素材不存在：{path.name}")
            suffix = path.suffix.lower() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else ".bin"
            remote_path = f"{remote_dir}/asset_{index:02d}{suffix}"
            copied = subprocess.run(
                ["scp", *self._ssh_base(), str(path), f"{ssh_target}:{remote_path}"],
                capture_output=True, text=True, timeout=120, check=False,
            )
            if copied.returncode != 0:
                raise RemoteExecutionError((copied.stderr or "素材上传新加坡失败")[-500:])
            remote_assets.append(remote_path)
        result = self._json("POST", "/job", {
            "task_id": project_id,
            "文案": script,
            "照片": remote_assets,
            "content_type": content_type,
            "source": "guangzhou-ai-video-factory",
        })
        job_id = str(result.get("job_id", ""))
        if not self._SAFE_ID.fullmatch(job_id):
            raise RemoteExecutionError("新加坡未返回有效任务编号")
        return job_id

    def status(self, job_id: str) -> dict[str, Any]:
        if not self._SAFE_ID.fullmatch(job_id):
            raise RemoteExecutionError("远程任务编号无效")
        return self._json("POST", "/job/status", {"job_id": job_id})

    def download(self, remote_path: str, destination: Path) -> Path:
        if not self._SAFE_RESULT.fullmatch(remote_path):
            raise RemoteExecutionError("远程成片路径不在允许目录")
        destination = Path(destination).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        ssh_target = f"{self.ssh_user}@{self.ssh_host}"
        copied = subprocess.run(
            ["scp", *self._ssh_base(), f"{ssh_target}:{remote_path}", str(temporary)],
            capture_output=True, text=True, timeout=300, check=False,
        )
        if copied.returncode != 0 or not temporary.is_file() or temporary.stat().st_size < 1024:
            temporary.unlink(missing_ok=True)
            raise RemoteExecutionError((copied.stderr or "新加坡成片回传失败")[-500:])
        temporary.replace(destination)
        return destination
