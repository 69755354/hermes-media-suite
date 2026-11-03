"""应用配置。敏感值只从环境变量读取。"""
# > 执行者：codex

from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
# 独立部署时源码目录不再嵌套于 workflow/projects；允许运维显式绑定
# 工作流单一事实源，同时保留原仓库布局的默认推导。
_repo_candidate = ROOT_DIR.parents[1]
if not (_repo_candidate / "wiki" / "spec" / "WORKFLOW_REGISTRY.yaml").is_file():
    _repo_candidate = Path("/home/ubuntu/workflow")
REPO_ROOT = Path(
    os.environ.get("XG_FACTORY_WORKFLOW_ROOT", str(_repo_candidate))
).resolve()
WEB_DIR = ROOT_DIR / "web"
CONFIG_DIR = ROOT_DIR / "config"
DEFAULT_PROJECTS_DIR = ROOT_DIR / "runtime" / "projects"
DEFAULT_DB_PATH = ROOT_DIR / "runtime" / "platform.sqlite3"
REGISTRY_PATH = REPO_ROOT / "wiki" / "spec" / "WORKFLOW_REGISTRY.yaml"
LABELS_PATH = REPO_ROOT / "wiki" / "spec" / "CLIENT_VIEW_LABELS.yaml"
CLIENT_VIEW_CATALOG_PATH = REPO_ROOT / "wiki" / "spec" / "CLIENT_VIEW_CATALOG.yaml"
INDUSTRY_SCHEMA_PATH = REPO_ROOT / "wiki" / "spec" / "INDUSTRY_FORM_SCHEMA.yaml"
DDL_PATH = REPO_ROOT / "scripts" / "ddl_platform.sql"
EXTENSION_DDL_PATH = ROOT_DIR / "config" / "platform_extensions.sql"

# MVP 硬约束：不实现自动发布，且不允许环境变量覆盖。
AUTO_PUBLISH_ENABLED = False

# Phase 1 默认关闭；即使运维显式打开，仍必须逐单写授权记录。
PAID_API_ENABLED = os.environ.get("PAID_API_ENABLED", "false").lower() == "true"


def host() -> str:
    return os.environ.get("XG_FACTORY_HOST", "127.0.0.1")


def port() -> int:
    value = int(os.environ.get("XG_FACTORY_PORT", "8090"))
    if not 1 <= value <= 65535:
        raise RuntimeError("XG_FACTORY_PORT 必须在 1-65535 之间")
    return value


def web_workers() -> int:
    """Uvicorn 进程数；4 核生产机默认一核一个 Web/队列 worker。"""
    value = int(os.environ.get("XG_FACTORY_WEB_WORKERS", "4"))
    if not 1 <= value <= 16:
        raise RuntimeError("XG_FACTORY_WEB_WORKERS 必须在 1-16 之间")
    return value


def request_threads() -> int:
    """每个 Uvicorn 进程的 AnyIO 同步请求线程上限。"""
    value = int(os.environ.get("XG_FACTORY_REQUEST_THREADS", "24"))
    if not 4 <= value <= 128:
        raise RuntimeError("XG_FACTORY_REQUEST_THREADS 必须在 4-128 之间")
    return value


def media_concurrency() -> int:
    """单机共享的 ffmpeg 并发槽位数。"""
    value = int(os.environ.get("XG_FACTORY_MEDIA_CONCURRENCY", "2"))
    if not 1 <= value <= 8:
        raise RuntimeError("XG_FACTORY_MEDIA_CONCURRENCY 必须在 1-8 之间")
    return value


def cookie_secure() -> bool:
    return os.environ.get("XG_FACTORY_COOKIE_SECURE", "0") == "1"


def reason_timeout_seconds() -> int:
    value = int(os.environ.get("XG_FACTORY_REASON_TIMEOUT", "420"))
    if not 30 <= value <= 900:
        raise RuntimeError("XG_FACTORY_REASON_TIMEOUT 必须在 30-900 秒之间")
    return value


def worker_poll_seconds() -> float:
    return max(0.1, min(float(os.environ.get("XG_FACTORY_WORKER_POLL", "0.5")), 5.0))


def worker_lease_seconds() -> int:
    value = int(os.environ.get("XG_FACTORY_WORKER_LEASE_SECONDS", "600"))
    if not 30 <= value <= 900:
        raise RuntimeError("XG_FACTORY_WORKER_LEASE_SECONDS 必须在 30-900 之间")
    return value


def worker_reconcile_seconds() -> int:
    value = int(os.environ.get("XG_FACTORY_WORKER_RECONCILE_SECONDS", "30"))
    if not 5 <= value <= 300:
        raise RuntimeError("XG_FACTORY_WORKER_RECONCILE_SECONDS 必须在 5-300 之间")
    return value


def remote_poll_batch() -> int:
    value = int(os.environ.get("XG_FACTORY_REMOTE_POLL_BATCH", "20"))
    if not 1 <= value <= 100:
        raise RuntimeError("XG_FACTORY_REMOTE_POLL_BATCH 必须在 1-100 之间")
    return value


def sqlite_busy_timeout_ms() -> int:
    value = int(os.environ.get("XG_FACTORY_SQLITE_BUSY_TIMEOUT_MS", "5000"))
    if not 1000 <= value <= 60000:
        raise RuntimeError("XG_FACTORY_SQLITE_BUSY_TIMEOUT_MS 必须在 1000-60000 之间")
    return value


def projects_dir() -> Path:
    return Path(os.environ.get("XG_FACTORY_PROJECTS_DIR", str(DEFAULT_PROJECTS_DIR))).resolve()


def database_path() -> Path:
    return Path(os.environ.get("XG_FACTORY_DB", str(DEFAULT_DB_PATH))).resolve()


def client_session_secret() -> str:
    value = os.environ.get("XG_FACTORY_SESSION_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("XG_FACTORY_SESSION_SECRET 必须至少 32 个字符")
    return value


def billing_base_url() -> str:
    return os.environ.get("XG_FACTORY_BILLING_BASE_URL", "http://127.0.0.1:18080").rstrip("/")


def billing_auth_token() -> str:
    return os.environ.get("XG_FACTORY_BILLING_AUTH_TOKEN", "")


def billing_admin_password() -> str:
    return os.environ.get("XG_FACTORY_BILLING_ADMIN_PASSWORD", "")


def billing_timeout_seconds() -> float:
    value = float(os.environ.get("XG_FACTORY_BILLING_TIMEOUT", "10"))
    if not 1 <= value <= 30:
        raise RuntimeError("XG_FACTORY_BILLING_TIMEOUT 必须在 1-30 秒之间")
    return value


def remote_codex_script() -> str:
    """广州业务节点调用新加坡 Codex 的唯一包装入口。"""
    return os.environ.get(
        "XG_FACTORY_REMOTE_CODEX_SCRIPT",
        "/home/ubuntu/.hermes/scripts/codex_remote.sh",
    ).strip()


def execution_base_url() -> str:
    """经 SSH 本地转发访问新加坡 Execute API，不暴露 1889 公网端口。"""
    return os.environ.get(
        "XG_FACTORY_EXECUTION_BASE_URL", "http://127.0.0.1:11889"
    ).rstrip("/")


def execution_timeout_seconds() -> float:
    value = float(os.environ.get("XG_FACTORY_EXECUTION_TIMEOUT", "20"))
    if not 3 <= value <= 60:
        raise RuntimeError("XG_FACTORY_EXECUTION_TIMEOUT 必须在 3-60 秒之间")
    return value


def execution_ssh_host() -> str:
    return os.environ.get("XG_FACTORY_EXECUTION_SSH_HOST", "<SG_HOST>").strip()


def execution_ssh_user() -> str:
    return os.environ.get("XG_FACTORY_EXECUTION_SSH_USER", "ubuntu").strip()


def execution_ssh_key() -> Path:
    return Path(
        os.environ.get(
            "XG_FACTORY_EXECUTION_SSH_KEY",
            "/home/ubuntu/.hermes/profiles/customer/home/.ssh/id_ed25519",
        )
    ).resolve()
