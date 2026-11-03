"""Multi-platform login slots (channel registry).

Requirement (source/extra-requirements-update.md section 3 + the user's request
2026-10-16): 抖音 / 星图 / 视频号 / 小红书 / 公众号, each as its OWN login slot,
and **extensible by configuration only** -- adding a platform must not touch
code.

One slot ("channel") owns:
  * its own browser profile directory (never shared: Mac background section 1 --
    a shared profile only ever yields account 1 data);
  * its own debug port (Chromium ``--remote-debugging-port``; the WebKit engine
    uses Playwright's own persistent-context protocol and therefore has no CDP
    port -- the field is then ``null`` and is reported as such, never faked);
  * its own status light;
  * its own offline alert (only the slot that dropped is announced).

Where the URLs come from
------------------------
``URL_VERIFIED`` marks a host the project files actually document.  Everything
else is a *configurable default* with ``needs_real_machine_confirmation: true``
-- we do not present a guessed backend path as a verified fact (VERIFY.md C5
carries the on-site checklist item).
"""

from __future__ import annotations

from .errors import ConfigError
from .jsonio import read_json

DEFAULT_PANEL_PORT = 9223

ENGINE_CHROMIUM = "chromium"
ENGINE_WEBKIT = "webkit"
ENGINE_CHROME = "chrome"      # 1.1.0 default: the CUSTOMER'S real Google Chrome
#: 1.1.0 (source/extra-requirements-chrome.md "用真谷歌"): every platform now
#: runs in the customer machine's real Chrome.  ``chromium`` is kept only so an
#: old channels.json still parses; it no longer implies an in-package Chromium.
ENGINE_CHROMIUM_LEGACY = ENGINE_CHROMIUM

#: Engines that speak CDP (so a per-slot ``--remote-debugging-port`` is real).
CDP_ENGINES = (ENGINE_CHROMIUM, ENGINE_CHROME)

# --------------------------------------------------------------------- presets
# login_url / check_url: `url_verified` records whether the host appears in the
# project's own files (source/win-local-agent-package-plan.md, agent code).
PLATFORM_PRESETS = {
    "douyin": {
        "name": "抖音",
        "profile": "douyin",
        "engine": ENGINE_CHROME,
        "login_url": "https://creator.douyin.com/",
        "check_url": "https://creator.douyin.com/",
        "cookie_domains": ["douyin.com"],
        "default_port": 9224,
        "url_verified": True,
        "url_source": "creator.douyin.com documented in agent/winport/"
                      "collect_douyin.py (creator centre) + plan section 6",
    },
    "xingtu": {
        "name": "星图",
        "profile": "xingtu",
        "engine": ENGINE_CHROME,
        "login_url": "https://www.xingtu.cn/",
        "check_url": "https://www.xingtu.cn/",
        "cookie_domains": ["xingtu.cn"],
        "default_port": 9225,
        "url_verified": False,
        "url_source": "host NOT recorded in the project files (plan only says "
                      "'星图后台'); confirm on the real machine before trusting",
    },
    "shipinhao": {
        "name": "视频号",
        "profile": "shipinhao",
        "engine": ENGINE_CHROME,
        "login_url": "https://channels.weixin.qq.com/",
        "check_url": "https://channels.weixin.qq.com/platform",
        "cookie_domains": ["weixin.qq.com", "qq.com"],
        "default_port": 9226,
        "url_verified": False,
        "url_source": "host NOT recorded in the project files (mac plan only "
                      "flags 视频号 feasibility as 待核验); confirm on site",
    },
    "xiaohongshu": {
        "name": "小红书",
        "profile": "xiaohongshu",
        "engine": ENGINE_CHROME,
        "login_url": "https://creator.xiaohongshu.com/",
        "check_url": "https://creator.xiaohongshu.com/",
        "cookie_domains": ["xiaohongshu.com"],
        "default_port": 9227,
        "url_verified": False,
        "url_source": "host NOT recorded in the project files; confirm on site",
    },
    "gongzhonghao": {
        "name": "公众号",
        "profile": "gongzhonghao",
        "engine": ENGINE_CHROME,
        "login_url": "https://mp.weixin.qq.com/",
        "check_url": "https://mp.weixin.qq.com/",
        "cookie_domains": ["weixin.qq.com", "qq.com"],
        "default_port": 9228,
        "url_verified": False,
        "url_source": "host NOT recorded in the project files; confirm on site",
    },
}

LOGIN_REDIRECT_HINTS = ("login", "signin", "sign-in", "passport", "auth")

#: "not given" (use the platform preset) vs an explicit ``null`` (no CDP port,
#: e.g. a WebKit slot) -- the two must not collapse into one another.
UNSET = object()


class Channel:
    """One login slot = one (platform, account) = one browser profile."""

    def __init__(self, channel_id, platform, *, nickname=None, engine=None,
                 profile=None, debug_port=UNSET, enabled=True, account_id=None,
                 login_url=None, check_url=None, cookie_domains=None,
                 url_verified=False, url_source=None, env_id=None):
        preset = PLATFORM_PRESETS.get(platform, {})
        self.channel_id = channel_id
        self.platform = platform
        self.env_id = env_id
        self.nickname = nickname or preset.get("name", platform)
        self.engine = engine or preset.get("engine", ENGINE_CHROME)
        self.profile_name = profile or preset.get("profile") or channel_id
        self.debug_port = preset.get("default_port") if debug_port is UNSET \
            else debug_port
        self.enabled = bool(enabled)
        self.account_id = account_id or channel_id
        self.login_url = login_url or preset.get("login_url")
        self.check_url = check_url or preset.get("check_url") or self.login_url
        self.cookie_domains = list(cookie_domains
                                   or preset.get("cookie_domains") or [])
        self.url_verified = bool(url_verified or preset.get("url_verified"))
        self.url_source = url_source or preset.get("url_source")
        self.platform_name = preset.get("name", platform)

    # -- identity / paths -------------------------------------------------
    @property
    def profile_key(self) -> str:
        return f"profiles/{self.profile_name}"

    def profile_dir(self, layout):
        return layout.profiles / self.profile_name

    @property
    def supports_cdp(self) -> bool:
        return self.engine in CDP_ENGINES and bool(self.debug_port)

    def cdp_url(self) -> str | None:
        if not self.supports_cdp:
            return None
        return f"http://127.0.0.1:{self.debug_port}"

    def describe(self) -> dict:
        return {
            "channel_id": self.channel_id,
            "platform": self.platform,
            "platform_name": self.platform_name,
            "nickname": self.nickname,
            "account_id": self.account_id,
            "engine": self.engine,
            "profile": self.profile_name,
            "debug_port": self.debug_port,
            "enabled": self.enabled,
            "login_url": self.login_url,
            "check_url": self.check_url,
            "cookie_domains": self.cookie_domains,
            "url_verified": self.url_verified,
            "url_source": self.url_source,
            "env_id": self.env_id,
        }

    def __repr__(self):
        return (f"<Channel {self.channel_id} platform={self.platform} "
                f"profile={self.profile_name} port={self.debug_port}>")


def channel_from_entry(entry: dict) -> Channel:
    if not isinstance(entry, dict):
        raise ConfigError("channels.json entries must be objects")
    if not entry.get("channel_id"):
        raise ConfigError("channels.json entry missing channel_id")
    platform = entry.get("platform")
    if not platform:
        raise ConfigError(f"channels.json entry {entry['channel_id']} missing platform")
    try:
        return Channel(
            entry["channel_id"], platform,
            nickname=entry.get("nickname"),
            engine=entry.get("engine"),
            profile=entry.get("profile"),
            debug_port=entry.get("debug_port", UNSET),
            enabled=entry.get("enabled", True),
            account_id=entry.get("account_id"),
            login_url=entry.get("login_url"),
            check_url=entry.get("check_url"),
            cookie_domains=entry.get("cookie_domains"),
            url_verified=entry.get("url_verified", False),
            url_source=entry.get("url_source"),
            env_id=entry.get("env_id"),
        )
    except ConfigError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise ConfigError(f"bad channels.json entry {entry.get('channel_id')}: {exc}")


def default_channels() -> list:
    """The five required platforms as ready-to-use slots (one slot each)."""
    out = []
    for platform, preset in PLATFORM_PRESETS.items():
        out.append(Channel(f"{platform}-001", platform))
    return out


def _covered_platforms(channels) -> set:
    return {c.platform for c in channels}


def load_channels(path, *, fallback_accounts=True, accounts_path=None) -> list:
    """Load the slot registry.

    Order: an explicit ``channels.json`` wins outright.  Otherwise the 1.0.0
    ``accounts.json`` slots are kept AND the five required platform defaults are
    added for every profile not already covered -- so an existing install gains
    星图 / 视频号 / 小红书 / 公众号 without losing its two 抖音 slots, and a
    brand-new install gets all five platforms.  Adding a platform is therefore
    "edit channels.json", never "edit code".
    """
    raw = read_json(path, default=None)
    if isinstance(raw, dict) and raw.get("channels"):
        return [channel_from_entry(e) for e in raw["channels"]]
    if isinstance(raw, list):
        return [channel_from_entry(e) for e in raw]
    channels = []
    if fallback_accounts and accounts_path is not None:
        accounts = read_json(accounts_path, default=None)
        entries = None
        if isinstance(accounts, dict):
            entries = accounts.get("accounts")
        elif isinstance(accounts, list):
            entries = accounts
        if entries:
            channels = [channel_from_entry({
                "channel_id": e.get("account_id"),
                "platform": e.get("platform", "douyin"),
                "nickname": e.get("nickname"),
                "engine": e.get("engine"),
                "profile": e.get("profile"),
                "debug_port": e.get("cdp_port"),
                "enabled": e.get("ready", True),
                "account_id": e.get("account_id"),
            }) for e in entries if e.get("account_id")]
    covered = _covered_platforms(channels)
    for preset in default_channels():
        if preset.platform not in covered:
            channels.append(preset)
    return channels or default_channels()


def load_registry(layout):
    """(environments, channels) for this installation.

    Source order (1.1.0):
      1. ``config/environments.json`` -> environments + expanded channels
         (the design-frozen model: one env, one profile, one port, many
         platforms);
      2. legacy ``config/channels.json`` (still honoured so an existing install
         keeps working after an in-place upgrade);
      3. the five platform presets as standalone slots.

    Adding a platform / environment is therefore a config edit only.
    """
    from .environments import expand_channels, load_environments
    envs = []
    try:
        envs = load_environments(layout.environments_file)
    except ConfigError:
        raise
    if envs:
        overrides = {}
        raw = read_json(layout.environments_file, default=None)
        if isinstance(raw, dict) and isinstance(raw.get("platform_overrides"), dict):
            overrides = raw["platform_overrides"]
        return envs, expand_channels(envs, overrides=overrides)
    channels = load_channels(layout.channels_file, accounts_path=layout.accounts_file)
    return [], channels


def panel_binding(raw_settings, raw_channels=None) -> dict:
    """Resolve the panel bind address (localhost only, by design)."""
    host, port = "127.0.0.1", DEFAULT_PANEL_PORT
    cfg = None
    if isinstance(raw_channels, dict):
        cfg = raw_channels.get("panel")
    elif isinstance(raw_settings, dict):
        cfg = raw_settings.get("panel")
    if isinstance(cfg, dict):
        host = cfg.get("host", host)
        port = int(cfg.get("port", port))
    return {"host": host, "port": port}
