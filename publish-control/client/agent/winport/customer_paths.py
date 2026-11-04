"""Per-customer data-area layout for the Windows publish worker.

The existing single-customer install keeps using the historical data root:

    %LOCALAPPDATA%\\HuolongAgent\\publish-worker\\
        inbox/  run/  out/  ...

A named customer is namespaced below ``customers/<customer_id>/``:

    %LOCALAPPDATA%\\HuolongAgent\\publish-worker\\customers\\<customer_id>\\
        inbox/  run/  out/  system/

``customer_id`` is deliberately *not* used as an unvalidated path component.
Only ``[a-z0-9._-]`` is accepted after normalisation (no separators, no
``..``).  Windows aliases are removed before the path is built: the id is
lower-cased, trailing dots are rejected, and DOS device names are rejected.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .secure_io import assert_no_reparse_chain, is_reparse_point

DEFAULT_CUSTOMER_ID = "default"
CUSTOMER_SUBDIRS = ("inbox", "run", "out", "system")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_RESERVED_NAMES = frozenset(
    ("con", "prn", "aux", "nul", "clock$")
    + tuple("com%d" % i for i in range(1, 10))
    + tuple("lpt%d" % i for i in range(1, 10))
)


class InvalidCustomerId(ValueError):
    """Raised when a customer id could escape the data area."""


class UnsafeCustomerRoot(ValueError):
    """Raised when a tenant root is a link/reparse point or resolves elsewhere."""


def normalize_customer_id(customer_id=None) -> str:
    """Return a safe canonical customer id.

    ``None``/empty means the legacy default.  The value is lower-cased so
    ``C1`` and ``c1`` cannot become two directories on a case-insensitive
    Windows volume.  Names ending in a dot and Windows DOS device names are
    rejected because Win32 strips or redirects them.
    """
    if customer_id is None:
        return DEFAULT_CUSTOMER_ID
    value = str(customer_id).strip()
    if not value:
        return DEFAULT_CUSTOMER_ID
    value = value.lower()
    if value == DEFAULT_CUSTOMER_ID:
        return DEFAULT_CUSTOMER_ID
    if not _ID_RE.match(value):
        raise InvalidCustomerId(f"invalid customer_id: {customer_id!r}")
    if value.endswith("."):
        raise InvalidCustomerId(
            f"invalid customer_id (trailing dot): {customer_id!r}")
    if value.split(".", 1)[0] in _RESERVED_NAMES:
        raise InvalidCustomerId(
            f"invalid customer_id (reserved Windows name): {customer_id!r}")
    return value


def is_legacy_customer(customer_id=None) -> bool:
    return normalize_customer_id(customer_id) == DEFAULT_CUSTOMER_ID


def customer_root(data_root, customer_id=None) -> Path:
    """Resolve the data root for one customer.

    ``default`` (or no id) intentionally returns *the original data root* so an
    in-place upgrade of an existing install keeps finding its inbox/run/out.
    """
    root = Path(data_root).expanduser()
    cid = normalize_customer_id(customer_id)
    if cid == DEFAULT_CUSTOMER_ID:
        # If the caller already passed a customer-scoped path, do not double
        # namespace it (idempotent resolution).
        if root.name == DEFAULT_CUSTOMER_ID and root.parent.name == "customers":
            return root
        return root
    if root.name == cid and root.parent.name == "customers":
        return root
    return root / "customers" / cid


def default_data_root() -> Path:
    """The same default the worker's ``paths.py`` uses, minus platform details."""
    env = os.environ.get("WINPORT_DATA")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "HuolongAgent" / "publish-worker"


class CustomerLayout:
    """A tiny path bundle for one customer.

    It is intentionally independent of the worker's larger ``Layout`` class so
    the poller can be tested on Linux.  When executing the real CLI the poller
    exports ``WINPORT_DATA`` / ``WINPORT_SYSTEM`` so the worker's own
    ``Layout`` resolves to the same directories.
    """

    def __init__(self, data_root=None, customer_id=None, *, scoped=True,
                 system_root=None):
        self.base = Path(data_root).expanduser() if data_root else default_data_root()
        self.customer_id = normalize_customer_id(customer_id)
        self.root = (customer_root(self.base, self.customer_id)
                     if scoped else self.base)
        self._system_root = (Path(system_root).expanduser()
                             if system_root else None)
        self.legacy = (not scoped) or self.customer_id == DEFAULT_CUSTOMER_ID
        self.validate()

    def validate(self) -> "CustomerLayout":
        """Prove the tenant root is a real directory in the trusted tree.

        The customer id is safe by construction, but an attacker can replace
        ``customers/<id>`` itself with a symlink or junction.  Resolving both
        the inbox and the root would then turn c2 into c1 and make a relative
        path check pass.  Reject the link at the root layer first, then compare
        the resolved root with the trusted ``base/customers/<id>`` path.
        """
        root = Path(os.path.abspath(os.fspath(self.root)))
        scoped_root = (root.name == self.customer_id
                       and root.parent.name == "customers")
        if scoped_root:
            trusted_base = root.parent.parent
            expected = trusted_base / "customers" / self.customer_id
        else:
            trusted_base = root
            expected = root

        try:
            assert_no_reparse_chain(root, root=trusted_base)
        except OSError as exc:
            raise UnsafeCustomerRoot(
                f"customer root is a link or reparse point: {root}") from exc
        if is_reparse_point(root):
            raise UnsafeCustomerRoot(
                f"customer root is a link or reparse point: {root}")
        try:
            resolved = root.resolve(strict=False)
            trusted = expected.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise UnsafeCustomerRoot(
                f"customer root cannot be resolved safely: {root}") from exc
        if os.path.normcase(str(resolved)) != os.path.normcase(str(trusted)):
            raise UnsafeCustomerRoot(
                f"customer root resolves outside its trusted path: {root}")
        return self

    @property
    def inbox(self) -> Path:
        return self.root / "inbox"

    @property
    def run(self) -> Path:
        return self.root / "run"

    @property
    def out(self) -> Path:
        return self.root / "out"

    @property
    def system(self) -> Path:
        # A dedicated machine keeps the historical %APPDATA% system area
        # (licence, clock state) instead of moving it under the data root.
        return self._system_root or (self.root / "system")

    # Common aliases used by the worker / report code.
    @property
    def outbox(self) -> Path:
        return self.out

    @property
    def out_reports(self) -> Path:
        return self.out / "reports"

    @property
    def logs(self) -> Path:
        return self.run / "logs"

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def profiles(self) -> Path:
        return self.root / "profiles"

    # The worker's ``Layout`` object exposes these names.  ``remote_ops`` and
    # the dry-run/licence code consume the same interface, so the customer
    # layout must provide them too instead of only the inbox/run/out roots.
    @property
    def settings_file(self) -> Path:
        return self.config / "settings.json"

    @property
    def environments_file(self) -> Path:
        return self.config / "environments.json"

    @property
    def channels_file(self) -> Path:
        return self.config / "channels.json"

    @property
    def accounts_file(self) -> Path:
        return self.config / "accounts.json"

    @property
    def license_file(self) -> Path:
        return self.system / "license.json"

    def ensure(self) -> "CustomerLayout":
        self.validate()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in CUSTOMER_SUBDIRS:
            if name == "system":
                self.system.mkdir(parents=True, exist_ok=True)
            else:
                (self.root / name).mkdir(parents=True, exist_ok=True)
        self.validate()
        return self

    def subdirs(self) -> dict:
        return {name: (self.system if name == "system" else self.root / name)
                for name in CUSTOMER_SUBDIRS}

    def describe(self) -> str:
        return (
            f"customer={self.customer_id}\n"
            f"root={self.root}\n"
            f"legacy={self.legacy}\n"
            f"inbox={self.inbox}\n"
            f"run={self.run}\n"
            f"out={self.out}\n"
            f"system={self.system}"
        )


# Convenience aliases used by deployment scripts / older call sites.
LEGACY_CUSTOMER_ID = DEFAULT_CUSTOMER_ID
data_root_for_customer = customer_root


def layout_for_customer(data_root_value=None, customer_id=None) -> CustomerLayout:
    return CustomerLayout(data_root=data_root_value, customer_id=customer_id)

def layout_dir(layout, name, default_rel=""):
    """Resolve one layout directory without eagerly touching ``layout.data``.

    ``CustomerLayout`` (the poller's path bundle) exposes ``root``/``system``
    but has no ``data`` attribute.  ``getattr(layout, name, Path(layout.data))``
    evaluated that default eagerly and raised AttributeError even when the
    attribute existed, which blocked every in-process dry-run.
    """
    value = getattr(layout, name, None)
    if value is not None:
        return Path(value)
    base = getattr(layout, "data", None) or getattr(layout, "root", None)
    if base is None:
        raise AttributeError("layout exposes neither %r nor data/root" % name)
    return Path(base) / default_rel if default_rel else Path(base)

