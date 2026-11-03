"""Customer self-service onboarding: machine code + offline licence import.

Why this exists: the customer installs the box themselves, with nobody on a
remote session.  The only two physical things they must do besides the install
are

  (1) send us the machine code the licence is bound to, and
  (2) put the licence we sign back onto the machine.

Both are a single double-click here, and both live in plain Python so the Linux
build host runs the *exact* code the Windows scripts call -- so the static
self-test can prove the chain instead of gesturing at a .ps1 nobody executed.

Hard constraint: this module only *imports* a licence the vendor already signed.
It never signs anything and there is no private key in the package (the signing
key lives on the control plane, see output/control-plane/sign_license.py).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .fingerprint import fingerprint
from .jsonio import read_json

#: written under <data>/logs/ ; non-ASCII on purpose -- it is a runtime file on
#: the customer's own machine, never part of the frozen package tree.
MACHINE_CODE_FILENAME = "机器码.txt"
LICENSE_FILENAME = "license.json"

#: statuses for which the signature AND the machine binding are both proven, so
#: installing the file is safe (an expired one still installs: the panel then
#: shows "已过期" instead of "未激活", which is the honest state).
_INSTALLABLE = ("OK", "GRACE", "EXPIRED")


def machine_code_info(components: dict | None = None) -> dict:
    """The machine-id the vendor binds a licence to, plus a little context.

    Only the component *names* are returned, never the raw GUIDs: the customer
    sends the machine code, not a dump of their hardware identifiers.
    ``components`` is injectable so the static (Linux) test can exercise the
    combine/hash path without a real Windows machine.
    """
    fp = fingerprint(components)
    return {
        "machine_id": fp["machine_id"],
        "platform": fp["platform"],
        "components_present": sorted(k for k, v in fp["components"].items() if v),
        "stable_component_count": fp["stable_component_count"],
        "weak": fp["weak"],
    }


def machine_code_text(info: dict, out_path=None) -> str:
    """The console / message-box page the customer copies from (plain text)."""
    lines = [
        "=" * 60,
        "漫剧发布助手 —— 机器码",
        "=" * 60,
        "",
        "机器码（请把下面这一整串发给我们，用来签发授权）：",
        "",
        "    " + info["machine_id"],
        "",
    ]
    if out_path is not None:
        lines += [f"（已保存到文件：{out_path}）", ""]
    lines += [
        "接下来（推荐：用激活码，最快）：",
        "  1. 双击桌面「漫剧发布助手」，打开面板。",
        "  2. 在激活码输入框填入我们发给你的 8 位激活码，",
        "     点「用激活码激活」，授权那一行变绿即可。",
        "     不用发机器码，也不用导入任何文件。",
        "",
        "备用方式（激活码用不了时）：",
        "  把这串机器码发给我们，我们发一个 license.json 给你，",
        "  在面板的授权区域选择这个文件导入即可。",
        "",
        "机器码也保存在：%LOCALAPPDATA%\\HuolongAgent\\publish-worker\\logs\\机器码.txt",
        "=" * 60,
    ]
    return "\n".join(lines)


def write_machine_code(layout, out=None, *, info=None) -> Path:
    """Write the machine code to ``<logs>/机器码.txt`` (or ``out``); return it."""
    info = info or machine_code_info()
    target = Path(out) if out else (Path(layout.logs) / MACHINE_CODE_FILENAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = machine_code_text(info, out_path=target)
    # A stable, machine-readable companion line helps support grep the file.
    payload += ("\n" + json.dumps({"machine_id": info["machine_id"],
                                   "platform": info["platform"],
                                   "components_present": info["components_present"]},
                                  ensure_ascii=False) + "\n")
    target.write_text(payload, encoding="utf-8", newline="\n")
    return target


def default_license_sources(layout, program=None) -> list:
    """Where a double-clicked 「导入授权」 looks for license.json, first match wins.

    Deliberately boring locations the customer can actually find:
      <Program>\\license\\license.json   (the folder we tell them to drop it in)
      <Program>\\license.json           (dropped next to the installer)
      <Desktop>\\license.json           (whatever they saved from our email)
    """
    program = Path(program or layout.program)
    home = Path.home()
    return [
        program / "license" / LICENSE_FILENAME,
        program / LICENSE_FILENAME,
        home / "Desktop" / LICENSE_FILENAME,
    ]


def find_license_file(layout, explicit=None, program=None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    for candidate in default_license_sources(layout, program=program):
        if candidate.exists():
            return candidate
    return None


def _install_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / (dst.name + ".incoming")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def import_license(layout, src, *, machine_id=None, fingerprint_info=None,
                   allow_test_injection=False, public_key_override=None,
                   install=True) -> dict:
    """Validate a signed licence for THIS machine and install it.

    Validation happens BEFORE anything is written: a corrupted file, a licence
    signed by the wrong key, or one bound to another machine must never turn the
    light green by accident.

    1.2.5 (GPT review 1.2.5 item 3): the trust root is the FIXED, non-overridable
    ``install_root()/config/vendor_pubkey.hex`` -- NOT ``layout.program`` and not
    any environment variable, so a caller can no longer point the import at
    their own key directory.  ``machine_id`` / ``fingerprint_info`` /
    ``public_key_override`` exist only for the static Linux harness and have no
    CLI flag that reaches them.
    """
    from .license import check_license, load_vendor_public_key, require_vendor_public_key

    src = Path(src)
    result = {
        "src": str(src),
        "license_file": str(layout.license_file),
        "installed": False,
    }
    obj = read_json(src, default=None)
    if not isinstance(obj, dict):
        result.update(status="NO_LICENSE_FILE",
                      reason=f"找不到或不是有效的授权文件：{src}")
        return result

    # 1.2.5: the trust root is read from its FIXED in-package location only
    # (GPT review items 3 / 5); a caller cannot point us at a different key.
    try:
        if allow_test_injection and public_key_override is not None:
            public_key = (public_key_override
                          if isinstance(public_key_override, (bytes, bytearray))
                          else load_vendor_public_key(public_key_override))
        else:
            public_key = require_vendor_public_key()   # FIXED trust root
    except Exception as exc:  # pragma: no cover - only when key is missing
        result.update(status="NO_VENDOR_KEY", reason=str(exc))
        return result

    fp = fingerprint_info if fingerprint_info is not None else fingerprint()
    effective_machine_id = machine_id or fp["machine_id"]
    verdict = check_license(obj, public_key, effective_machine_id,
                            fingerprint_info=fp)
    status = verdict["status"]
    result.update(status=status, reason=verdict.get("reason", ""),
                  days_left=verdict.get("days_left"),
                  machine_id=effective_machine_id,
                  licence_machine_id=obj.get("machine_id"),
                  customer_id=obj.get("customer_id"))
    if status in _INSTALLABLE:
        if install:
            _install_atomic(src, Path(layout.license_file))
            result["installed"] = True
            result["reason"] = {
                "OK": "授权已导入并生效。",
                "GRACE": "授权已导入；当前在离线宽限期内，请尽快续期。",
                "EXPIRED": "授权已导入，但已过期：新增发布暂停，抓数与历史数据不受影响，续期后自动恢复。",
            }.get(status, verdict.get("reason", ""))
        else:
            # 1.2.5 round-3 (GPT review N1): --dry-run means VALIDATE ONLY.  The
            # validation above already ran; do NOT write the licence file.
            result["installed"] = False
            result["dry_run"] = True
            result["reason"] = ("仅校验（--dry-run）：授权有效，未写入安装；"
                                "去掉 --dry-run 才会安装。")
    return result


def license_import_text(result: dict) -> str:
    """Plain-text page for the console / message box."""
    installed = result.get("installed")
    dry_run = result.get("dry_run")
    status = result.get("status", "")
    # 1.2.5 round-6/round-7 (GPT review N1): --dry-run on a VALID licence must
    # not say "授权导入失败", and --dry-run on an INVALID one must not claim
    # "校验通过".  Key the title/advice on the VALIDATION status, not just the
    # dry-run flag.
    valid = status in ("OK", "GRACE", "EXPIRED")
    if installed:
        head = "授权导入成功"
    elif dry_run and valid:
        head = "授权校验通过（未安装 / --dry-run）"
    else:
        head = "授权导入失败"
    lines = ["=" * 60, f"漫剧发布助手 —— {head}", "=" * 60, ""]
    lines.append(result.get("reason", ""))
    lines.append("")
    if installed:
        lines += [
            f"授权文件位置：{result['license_file']}",
            f"授权机器码：  {result.get('licence_machine_id', '')}",
            f"本机机器码：  {result.get('machine_id', '')}",
            "",
            "现在可以双击桌面「漫剧发布助手」查看：",
            "顶部「授权」那一行应显示为绿色（有效）。",
        ]
    elif dry_run and valid:
        lines += [
            f"状态：{status}",
            f"来源文件：{result.get('src', '')}",
            "",
            "本次是 --dry-run（仅校验），没有写入安装。",
            "去掉 --dry-run 重新运行即可正式导入。",
        ]
    else:
        lines += [
            f"状态：{result.get('status', '')}",
            f"来源文件：{result.get('src', '')}",
            "",
            "请把这一页截图发给我们，我们会重新签发或核对机器码。",
        ]
    lines += ["=" * 60]
    return "\n".join(lines)
