"""Automatic enrolment; the customer runtime contains only signature verifiers."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
import ssl
import socket

from .paths import install_root
from .licstate import read_license_file, unified_license_state
from .fingerprint import fingerprint
from . import control_status

_LOCK = threading.Lock()
MAX_RESPONSE = 256 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('激活服务重定向被拒绝')


CODE_ENDPOINT = 'https://xingturgzn.cn/v1/activate'
CODE_LENGTH = 8
CODE_MIN_LENGTH = CODE_LENGTH
PINNED_HOST = 'xingturgzn.cn'
CODE_RE = re.compile(r'[A-Za-z0-9]{8}\Z')
CONTROL_FIELDS = (
    'control_url', 'customer_id', 'customer_token',
    'device_id', 'device_token', 'binding_epoch',
)


def normalize_code(raw):
    """Return an 8-character ASCII code, or "" when the input is not one."""
    if not isinstance(raw, str):
        return ''
    code = raw.strip()
    if CODE_RE.fullmatch(code) is None:
        return ''
    return code.upper()


def is_valid_control(control):
    """True when an activate response carries a usable control binding."""
    if not isinstance(control, dict):
        return False
    if any(field not in control for field in CONTROL_FIELDS):
        return False
    url = control.get('control_url')
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme.lower() != 'https' or not parsed.hostname:
        return False
    for field in ('customer_id', 'device_id',
                  'customer_token', 'device_token'):
        value = control.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def _write_control_config(layout, control):
    """Atomically persist the server-issued control binding with mode 0600."""
    target = Path(layout.data) / 'control.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.control-', suffix='.json',
                                dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(control, out, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(name, 0o600)
        os.replace(name, target)
        os.chmod(target, 0o600)
    finally:
        Path(name).unlink(missing_ok=True)


def _control_error_text(response) -> str:
    value = response.get('control_error') if isinstance(response, dict) else None
    if not value:
        return ''
    text = str(value).replace('\r', ' ').replace('\n', ' ').strip()
    return text[:control_status.MAX_REASON]


def _set_control_status(layout, state, reason='', control=None) -> None:
    """Best-effort customer-visible status; never includes a token."""
    try:
        data = control if isinstance(control, dict) else {}
        control_status.write_status(
            layout, state, reason,
            customer_id=str(data.get('customer_id') or ''),
            device_id=str(data.get('device_id') or ''))
    except Exception:  # noqa: BLE001 - status must never break activation
        logging.getLogger(__name__).warning('could not write control status')


def _has_valid_control(layout) -> bool:
    candidates = [Path(layout.data) / 'control.json']
    program = getattr(layout, 'program', None)
    if program:
        candidates.append(Path(program) / 'control.json')
    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            continue
        if is_valid_control(data):
            return True
    return False


def _bridge_control(layout, response):
    """Persist the control binding and return (ok, reason, state)."""
    control = response.get('control') if isinstance(response, dict) else None
    control_error = _control_error_text(response)
    if is_valid_control(control):
        try:
            _write_control_config(layout, control)
        except Exception:  # noqa: BLE001 - licence stays valid; report honestly
            reason = '接入配置保存失败，请联系服务商。'
            _set_control_status(layout, 'error', reason, control)
            return False, reason, 'error'
        _set_control_status(layout, 'connected', '', control)
        return True, '接入已补齐', 'connected'
    if control_error:
        _set_control_status(layout, 'error', control_error, control)
        return False, control_error, 'error'
    reason = '服务端未返回接入配置'
    _set_control_status(layout, 'missing', reason, control)
    return False, reason, 'missing'


def _install_with_control(layout, document, response):
    """Install the licence, then bridge a valid control binding to disk."""
    result = install_document(layout, document)
    if not result.get('ok'):
        return result
    control_ok, control_reason, control_state = _bridge_control(layout, response)
    reason = ('授权已生效，接入已补齐' if control_ok else
              '授权已生效，但接入未完成：' + control_reason)
    return {**result, 'reason': reason, 'control_state': control_state,
            'control_ok': control_ok}


def _complete_existing_control(layout, response):
    """An existing formal licence stays installed; only bridge control."""
    control_ok, control_reason, control_state = _bridge_control(layout, response)
    reason = ('授权已生效，接入已补齐' if control_ok else
              '授权已生效，但接入未完成：' + control_reason)
    return {'ok': True, 'reason': reason, 'control_state': control_state,
            'control_ok': control_ok}


def _existing_incomplete(layout, reason):
    _set_control_status(layout, 'error', reason)
    return {'ok': True,
            'reason': '授权已生效，但接入未完成：' + reason,
            'control_state': 'error', 'control_ok': False}


def _formal(state) -> bool:
    return bool(state.get('publish_allowed')) and state.get('source') != 'trial'


def exchange(token, machine_id):
    parsed = urlsplit(CODE_ENDPOINT)
    if (parsed.scheme != 'https' or parsed.hostname != PINNED_HOST
            or parsed.username or parsed.password
            or parsed.path != '/v1/activate' or parsed.fragment or parsed.query
            or not isinstance(token, str) or not isinstance(machine_id, str)
            or len(token) < CODE_LENGTH):
        raise ValueError('安装包激活信息不完整，请联系服务商重新提供安装包')
    request = Request(CODE_ENDPOINT,
                      data=json.dumps({'machine_id': machine_id}).encode(),
                      headers={'Content-Type': 'application/json',
                               'Authorization': 'Bearer ' + token}, method='POST')
    # Default TLS certificate validation; never send credentials across redirects.
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError('激活服务拒绝请求')
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('激活响应超过大小限制')
    obj = json.loads(raw)
    if not isinstance(obj, dict) or not isinstance(obj.get('license'), dict):
        raise ValueError('激活响应格式错误')
    return obj


def activate_with_code(layout, code):
    """Redeem a short enrolment code typed by the customer.

    The code is not a secret that grants blanket access: the server binds it to
    the first machine that redeems it and can revoke it.  One generic package
    therefore serves every customer.
    """
    normalized = normalize_code(code)
    if len(normalized) != CODE_LENGTH:
        return {'ok': False, 'reason': '激活码格式不对，请核对后重试'}
    existing_before = False
    try:
        with _LOCK:
            state = unified_license_state(layout)
            existing_before = _formal(state)
            if existing_before:
                if state.get('tombstone_error') and _has_valid_control(layout):
                    return {'ok': False,
                            'reason': '已有授权，但防回放墓碑仍无法写入；'
                                      '请重试或联系服务商。'}
                if _has_valid_control(layout):
                    return {'ok': True, 'reason': '已有有效授权，无需再次激活',
                            'control_state': 'connected', 'control_ok': True}
        response = exchange(normalized, fingerprint()['machine_id'])
        with _LOCK:
            state = unified_license_state(layout)
            if _formal(state):
                if state.get('tombstone_error') and _has_valid_control(layout):
                    return {'ok': False,
                            'reason': '已有授权，但防回放墓碑仍无法写入；'
                                      '请重试或联系服务商。'}
                return _complete_existing_control(layout, response)
            return _install_with_control(layout, response.get('license') or {},
                                         response)
    except HTTPError as exc:
        reason = f'激活服务返回 HTTP {exc.code}；请核对激活码或联系服务商。'
    except (TimeoutError, socket.timeout):
        reason = '连接激活服务超时；请恢复网络后重试。'
    except URLError as exc:
        reason = ('激活服务证书校验失败；请联系服务商。'
                  if isinstance(exc.reason, ssl.SSLError)
                  else '无法连接激活服务；请检查网络后重试。')
    except PermissionError:
        reason = '授权文件无法写入：当前用户权限不足；请联系服务商。'
    except OSError:
        reason = '授权文件读写失败或网络中断；请检查磁盘空间、网络，并联系服务商。'
    except (ValueError, TypeError, AttributeError):
        reason = '激活码无效或已被使用；请向服务商索取新的激活码。'
    except Exception:
        reason = '激活过程发生内部错误；请联系服务商。'
    if existing_before:
        return _existing_incomplete(layout, reason)
    return {'ok': False, 'reason': reason}


def install_document(layout, document, *, overwrite=False):
    """Use the SAME trust root, machine, expiry and clock verdict before replace."""
    dst = Path(layout.license_file)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if overwrite is not True:
        existing = read_license_file(dst)
        old = existing['obj'] if existing['kind'] == 'ok' else None
        new_mid = document.get('machine_id') if isinstance(document, dict) else None
        if (isinstance(old, dict) and isinstance(new_mid, str)
                and old.get('machine_id') == new_mid):
            state = unified_license_state(layout)
            if (state.get('status') == 'OK' and state.get('publish_allowed')
                    and (state.get('days_left') or 0) > 0):
                return {'ok': False,
                        'reason': '\u672c\u673a\u5df2\u6709\u6709\u6548\u6388\u6743\uff1b'
                                  '\u5982\u786e\u9700\u8986\u76d6\u8bf7\u663e\u5f0f\u786e\u8ba4\u3002'}
    fd, name = tempfile.mkstemp(prefix='.activation-', suffix='.json', dir=dst.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(document, out, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        state = unified_license_state(layout, license_path=name)
        if not state['publish_allowed']:
            return {'ok': False, 'reason': state['text']}
        try:
            from .license import mark_trial_license_seen
            mark_trial_license_seen(layout)
        except OSError as exc:
            return {'ok': False,
                    'reason': '授权校验通过，但防回放墓碑写入失败：%s；'
                              '本次未安装授权，请重试或联系服务商。' % exc,
                    'tombstone_error': True}
        os.replace(name, dst)
        return {'ok': True, 'reason': '授权已自动生效'}
    finally:
        Path(name).unlink(missing_ok=True)


def activate(layout):
    existing_before = False
    try:
        with _LOCK:
            state = unified_license_state(layout)
            existing_before = _formal(state)
            if existing_before:
                if state.get('tombstone_error') and _has_valid_control(layout):
                    return {'ok': False,
                            'reason': '已有授权，但防回放墓碑仍无法写入；'
                                      '请重试或联系服务商。'}
                if _has_valid_control(layout):
                    return {'ok': True, 'reason': '已有有效授权，无需联网',
                            'control_state': 'connected', 'control_ok': True}
            else:
                bundled = install_root() / 'license' / 'license.json'
                if bundled.is_file():
                    result = install_document(layout, json.loads(bundled.read_text(encoding='utf-8-sig')))
                    if result['ok']:
                        return result
        config_path = install_root() / 'config' / 'activation.json'
        if not config_path.is_file():
            if existing_before:
                reason = ('安装包没有自动接入信息，请在激活码框输入服务商提供的 '
                          '8 位激活码，再点「重新获取接入配置」。')
                _set_control_status(layout, 'missing', reason)
                return {'ok': True,
                        'reason': '授权已生效，但接入未完成：' + reason,
                        'control_state': 'missing', 'control_ok': False}
            return {'ok': False,
                    'reason': '安装包没有自动激活信息。请点面板顶部「查看机器码」，'
                              '把机器码发给服务商换取 8 位激活码，填入面板「激活码」框后'
                              '点「用激活码激活」；也可让服务商签发 license.json，'
                              '再用包内 import-license.bat 导入。'}
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        endpoint = config.get('endpoint')
        if endpoint is not None and endpoint != CODE_ENDPOINT:
            logging.getLogger(__name__).warning(
                'activation.json endpoint ignored; pinned endpoint in use')
        response = exchange(config.get('enrollment_token', ''),
                            fingerprint()['machine_id'])
        with _LOCK:
            state = unified_license_state(layout)
            if _formal(state):
                if state.get('tombstone_error') and _has_valid_control(layout):
                    return {'ok': False,
                            'reason': '已有授权，但防回放墓碑仍无法写入；'
                                      '请重试或联系服务商。'}
                return _complete_existing_control(layout, response)
            return _install_with_control(layout, response.get('license') or {},
                                         response)
    except HTTPError as exc:
        reason = f'授权服务返回 HTTP {exc.code}；请联系服务商核对授权状态。'
    except (TimeoutError, socket.timeout):
        reason = '连接授权服务超时；请恢复网络后重试。'
    except URLError as exc:
        reason = ('授权服务证书校验失败；请联系服务商。'
                  if isinstance(exc.reason, ssl.SSLError)
                  else '无法连接授权服务；请检查网络后重试。')
    except PermissionError:
        reason = '授权文件无法写入：当前用户权限不足；请联系服务商。'
    except OSError:
        reason = '授权文件读写失败或网络中断；请检查磁盘空间、网络，并联系服务商。'
    except (ValueError, TypeError, AttributeError):
        reason = '安装包激活信息或服务返回数据无效；请联系服务商。'
    except Exception:
        reason = '自动授权发生内部错误；请联系服务商。'
    if existing_before:
        return _existing_incomplete(layout, reason)
    # Never expose URLs, credentials, HTTP bodies or raw exceptions.
    return {'ok': False, 'reason': reason + ' 新增发布保持暂停，已有数据保留。'}


def refresh_control(layout, code=None):
    """Panel button: run one exchange to (re)provision control.json.

    A code is preferred.  Without one, a package that still carries an
    enrolment token may use the normal activation path; otherwise the customer
    is told to type the activation code first.
    """
    normalized = normalize_code(code) if code else ''
    if normalized:
        return activate_with_code(layout, normalized)
    if code not in (None, ''):
        return {'ok': False, 'reason': '激活码格式不对，请核对后重试'}
    config_path = install_root() / 'config' / 'activation.json'
    if config_path.is_file():
        return activate(layout)
    state = unified_license_state(layout)
    if _formal(state):
        reason = ('请在激活码框输入服务商提供的 8 位激活码，'
                  '再点「重新获取接入配置」。')
        _set_control_status(layout, 'missing', reason)
        return {'ok': True, 'reason': '授权已生效，但接入未完成：' + reason,
                'control_state': 'missing', 'control_ok': False}
    return {'ok': False,
            'reason': '请先在激活码框输入服务商提供的 8 位激活码，'
                      '再点「重新获取接入配置」。'}


def main():
    import argparse
    from .paths import Layout
    parser = argparse.ArgumentParser()
    parser.add_argument('--data')
    args = parser.parse_args()
    result = activate(Layout(data=args.data).ensure())
    print(result['reason'], flush=True)
    return 0 if result['ok'] else 5


if __name__ == '__main__':
    raise SystemExit(main())
