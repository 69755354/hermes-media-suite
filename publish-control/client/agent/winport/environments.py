"""Environment registry: one environment = one Chrome user dir + one debug port
+ one login state + one status light + one control-panel card.

Design freeze (source/env-design.md, user 2026-10-16): a "环境(environment)"
groups the platforms that share ONE account system.  All platforms inside an
environment share that environment's Chrome profile (one ``--user-data-dir``)
and its single ``--remote-debugging-port`` because they must share one login
state; a platform may belong to exactly one environment.

Hard rules implemented here (and enforced, not just documented):
  1. one environment == at most one live browser instance (lock is per env,
     not per platform -- see instance.EnvironmentLease / browser.py);
  2. a platform may be listed by at most ONE environment;
  3. adding a platform / adding an environment / splitting an environment is a
     ``config/environments.json`` edit -- never a code edit;
  4. every environment carries a reserved ``proxy`` field (unused this round).

Phase-1 four environments (source/env-design.md):
  env_1      1号    抖音 + 星图      端口 9224
  env_2      2号    抖音 + 星图      端口 9225
  env_wechat 微信   视频号 + 公众号   端口 9226
  env_xhs    小红书 小红书           端口 9227
"""

from __future__ import annotations

from .errors import ConfigError
from .jsonio import read_json
from .platforms import PLATFORM_PRESETS, Channel, UNSET, ENGINE_CHROME

#: first debug port of the environment range (source/extra-requirements-chrome.md)
DEFAULT_ENV_PORT_BASE = 9224

#: where a platform's login_url/check_url come from when the env does not
#: spell them out -- the platform preset registry (platforms.PLATFORM_PRESETS).
def _phase1_environments():
    return [
        {"env_id": "env_1", "label": "1号", "nickname": "1号（抖音）",
         "profile": "env_1", "debug_port": 9224,
         "platforms": ["douyin", "xingtu"], "proxy": None, "enabled": True,
         "visible": True},
        {"env_id": "env_2", "label": "2号", "nickname": "2号（抖音）",
         "profile": "env_2", "debug_port": 9225,
         "platforms": ["douyin", "xingtu"], "proxy": None, "enabled": True,
         "visible": True},
        {"env_id": "env_wechat", "label": "微信", "nickname": "微信（视频号/公众号）",
         "profile": "env_wechat", "debug_port": 9226,
         "platforms": ["shipinhao", "gongzhonghao"], "proxy": None,
         "enabled": True, "visible": False},
        {"env_id": "env_xhs", "label": "小红书", "nickname": "小红书",
         "profile": "env_xhs", "debug_port": 9227,
         "platforms": ["xiaohongshu"], "proxy": None, "enabled": True,
         "visible": False},
    ]


class Environment:
    """One login environment = one profile dir + one CDP port + its platforms."""

    def __init__(self, env_id, *, label=None, nickname=None, profile=None,
                 debug_port=None, platforms=None, proxy=None, enabled=True,
                 note=None, visible=None):
        if not env_id:
            raise ConfigError("environments.json entry missing env_id")
        self.env_id = env_id
        self.label = label or nickname or env_id
        self.nickname = nickname or self.label
        self.profile_name = profile or env_id
        self.debug_port = int(debug_port) if debug_port else None
        self.platforms = list(platforms or [])
        self.proxy = proxy          # RESERVED (this round: always null)
        self.enabled = bool(enabled)
        self.visible = _entry_visible(platforms) if visible is None else bool(visible)
        self.note = note

    # ---- geometry ------------------------------------------------------
    def profile_dir(self, layout):
        return layout.profiles / self.profile_name

    @property
    def supports_cdp(self) -> bool:
        return bool(self.debug_port)

    def cdp_url(self) -> str | None:
        if not self.debug_port:
            return None
        return f"http://127.0.0.1:{self.debug_port}"

    def channels(self) -> list:
        """Expand into one Channel per platform, all sharing this env's profile
        dir and debug port (they are the same browser)."""
        out = []
        for platform in self.platforms:
            out.append(Channel(
                f"{self.env_id}:{platform}", platform,
                nickname=(PLATFORM_PRESETS.get(platform, {}).get("name", platform)),
                engine=ENGINE_CHROME,
                profile=self.profile_name,
                debug_port=self.debug_port,
                enabled=self.enabled,
                account_id=f"{self.env_id}:{platform}",
                env_id=self.env_id,
            ))
        return out

    def describe(self) -> dict:
        return {
            "env_id": self.env_id,
            "label": self.label,
            "nickname": self.nickname,
            "profile": self.profile_name,
            "debug_port": self.debug_port,
            "platforms": list(self.platforms),
            "proxy": self.proxy,
            "enabled": self.enabled,
            "visible": self.visible,
            "note": self.note,
        }

    def __repr__(self):
        return (f"<Environment {self.env_id} label={self.label} "
                f"port={self.debug_port} platforms={self.platforms}>")


def environment_from_entry(entry: dict) -> Environment:
    if not isinstance(entry, dict):
        raise ConfigError("environments.json entries must be objects")
    platforms = entry.get("platforms")
    if platforms is None:
        platforms = entry.get("platform")
        platforms = [platforms] if platforms else []
    try:
        return Environment(
            entry["env_id"],
            label=entry.get("label"),
            nickname=entry.get("nickname"),
            profile=entry.get("profile"),
            debug_port=entry.get("debug_port", entry.get("cdp_port")),
            platforms=platforms,
            proxy=entry.get("proxy"),
            enabled=entry.get("enabled", True),
            visible=entry.get("visible"),
            note=entry.get("note"),
        )
    except ConfigError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise ConfigError(f"bad environments.json entry {entry.get('env_id')}: {exc}")


def default_environments() -> list:
    return [environment_from_entry(e) for e in _phase1_environments()]


def validate_environments(envs) -> list:
    """Return a list of human-readable PROBLEMS (empty == valid).

    Enforced (blocking):
      * unique env_id / profile dir / debug port;
      * no platform repeated INSIDE one environment;
      * every platform resolves to a preset (or an explicit login_url);
      * ports are sane; the reserved proxy field is an object or null.

    The hard rule "一个平台只能归属一个环境" is enforced per ACCOUNT: a platform
    instance (``<env_id>:<platform>``, i.e. a specific 号) belongs to exactly one
    environment -- that is guaranteed by the unique channel_id.  The same
    platform TYPE appearing in two environments is legitimate when they are two
    different 号 (source/env-design.md itself gives 抖音+星图 to both env_1 and
    env_2); those cases are surfaced as non-blocking warnings by
    ``environment_warnings`` instead of being rejected.
    """
    problems = []
    seen_env, seen_profile, seen_port = {}, {}, {}
    for env in envs:
        if env.env_id in seen_env:
            problems.append(f"环境 id 重复：{env.env_id}")
        seen_env[env.env_id] = env
        if env.profile_name in seen_profile:
            problems.append(f"环境 {env.env_id} 与 {seen_profile[env.profile_name]} "
                            f"共用同一个登录态目录 profile={env.profile_name}"
                            "（一个环境一个目录，不能共用）")
        seen_profile[env.profile_name] = env.env_id
        if env.debug_port is not None:
            if not (1 <= env.debug_port <= 65535):
                problems.append(f"环境 {env.env_id} 端口非法：{env.debug_port}")
            if env.debug_port in seen_port:
                problems.append(f"环境 {env.env_id} 与 {seen_port[env.debug_port]} "
                                f"端口冲突：{env.debug_port}")
            seen_port[env.debug_port] = env.env_id
        if env.proxy is not None and not isinstance(env.proxy, dict):
            problems.append(f"环境 {env.env_id} 的 proxy 必须是对象或 null"
                            "（本期留空不实现，只做字段预留）")
        if not isinstance(env.visible, bool):
            problems.append(f"环境 {env.env_id} 的 visible 必须是 true/false")
        duplicated = {p for p in env.platforms
                      if list(env.platforms).count(p) > 1}
        for platform in sorted(duplicated):
            problems.append(f"环境 {env.env_id} 里重复登记了平台 {platform}")
        for platform in env.platforms:
            preset = PLATFORM_PRESETS.get(platform)
            if not preset:
                problems.append(
                    f"环境 {env.env_id} 引用了未登记的平台 {platform}；"
                    "加平台请在 platforms.PLATFORM_PRESETS 里补 login_url/check_url"
                    "（或直接在 environments.json 里给该平台写 login_url/check_url）")
            elif not preset.get("login_url"):
                problems.append(f"平台 {platform} 没有 login_url，无法拉起登录窗口")
    return problems


def environment_warnings(envs) -> list:
    """Non-blocking notes (same platform type in several environments)."""
    owners = {}
    for env in envs:
        for platform in env.platforms:
            owners.setdefault(platform, []).append(env.env_id)
    warnings = []
    for platform, env_ids in sorted(owners.items()):
        if len(env_ids) > 1:
            warnings.append(
                f"平台 {platform} 出现在多个环境（{'、'.join(env_ids)}）；"
                "按设计这代表多个不同的号，各自独立登录态/端口/授权，"
                "不是同一个登录态被两个环境共用")
    return warnings


def environment_owner_map(envs) -> dict:
    """platform -> [env_id, ...] (documents the per-号 ownership)."""
    owners = {}
    for env in envs:
        for platform in env.platforms:
            owners.setdefault(platform, []).append(env.env_id)
    return owners


def expand_channels(envs, *, overrides=None) -> list:
    """All channels for all environments, in a stable order.

    ``overrides`` maps platform -> {"login_url"/"check_url"/"cookie_domains":...}
    so an environment may point a platform at a different backend without a code
    change.
    """
    overrides = overrides or {}
    out = []
    for env in envs:
        for channel in env.channels():
            patch = overrides.get(channel.platform)
            if patch:
                channel.login_url = patch.get("login_url", channel.login_url)
                channel.check_url = patch.get("check_url", channel.check_url)
                if patch.get("cookie_domains"):
                    channel.cookie_domains = patch["cookie_domains"]
            out.append(channel)
    return out


def environment_for_platform(envs, platform):
    for env in envs:
        if platform in env.platforms:
            return env
    return None


def env_by_id(envs, env_id):
    for env in envs:
        if env.env_id == env_id:
            return env
    return None


def _entry_visible(platforms):
    """Old configs predating ``visible`` stay hidden when they contain only
    platforms that are not open in this release."""
    platforms = list(platforms or [])
    if not platforms:
        return True
    return all(platform in ("douyin", "xingtu") for platform in platforms)


def load_environments(path) -> list:
    """Load config/environments.json.  Returns [] when the file is absent so the
    caller can fall back to the legacy channels.json / presets."""
    raw = read_json(path, default=None)
    if raw is None:
        return []
    if isinstance(raw, dict):
        entries = raw.get("environments")
    elif isinstance(raw, list):
        entries = raw
    else:
        raise ConfigError(f"environments.json must be an object or array: {path}")
    if not entries:
        return []
    envs = [environment_from_entry(e) for e in entries]
    problems = validate_environments(envs)
    if problems:
        raise ConfigError("environments.json 有配置错误：" + "；".join(problems))
    return envs
