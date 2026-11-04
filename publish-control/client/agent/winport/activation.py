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


def normalize_code(raw):
    """Return an 8-character ASCII code, or "" when the input is not one."""
    if not isinstance(raw, str):
        return ''
    code = raw.strip()
    if CODE_RE.fullmatch(code) is None:
        return ''
    return code.upper()


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
    return obj['license']


def activate_with_code(layout, code):
    """Redeem a short enrolment code typed by the customer.

    The code is not a secret that grants blanket access: the server binds it to
    the first machine that redeems it and can revoke it.  One generic package
    therefore serves every customer.
    """
    normalized = normalize_code(code)
    if len(normalized) != CODE_LENGTH:
        return {'ok': False, 'reason': '激活码格式不对，请核对后重试'}
    try:
        with _LOCK:
            state = unified_license_state(layout)
            if state['publish_allowed'] and state.get('source') != 'trial':
                if state.get('tombstone_error'):
                    return {'ok': False,
                            'reason': '已有授权，但防回放墓碑仍无法写入；'
                                      '请重试或联系服务商。'}
                return {'ok': True, 'reason': '已有有效授权，无需再次激活'}
        document = exchange(normalized, fingerprint()['machine_id'])
        with _LOCK:
            state = unified_license_state(layout)
            if state['publish_allowed'] and state.get('source') != 'trial':
                if state.get('tombstone_error'):
                    return {'ok': False,
                            'reason': '已有授权，但防回放墓碑仍无法写入；'
                                      '请重试或联系服务商。'}
                return {'ok': True, 'reason': '已有有效授权，无需再次激活'}
            return install_document(layout, document)
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
    try:
        with _LOCK:
            state = unified_license_state(layout)
            if state['publish_allowed'] and state.get('source') != 'trial':
                if state.get('tombstone_error'):
                    return {'ok': False,
                            'reason': '已有授权，但防回放墓碑仍无法写入；'
                                      '请重试或联系服务商。'}
                return {'ok': True, 'reason': '已有有效授权，无需联网'}
            bundled = install_root() / 'license' / 'license.json'
            if bundled.is_file():
                result = install_document(layout, json.loads(bundled.read_text(encoding='utf-8-sig')))
                if result['ok']:
                    return result
        config_path = install_root() / 'config' / 'activation.json'
        if not config_path.is_file():
            return {'ok': False, 'reason': '安装包缺少自动激活信息，请联系服务商；无需自行导入授权。'}
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        endpoint = config.get('endpoint')
        if endpoint is not None and endpoint != CODE_ENDPOINT:
            logging.getLogger(__name__).warning(
                'activation.json endpoint ignored; pinned endpoint in use')
        document = exchange(config.get('enrollment_token', ''),
                            fingerprint()['machine_id'])
        with _LOCK:
            state = unified_license_state(layout)
            if state['publish_allowed'] and state.get('source') != 'trial':
                if state.get('tombstone_error'):
                    return {'ok': False,
                            'reason': '已有授权，但防回放墓碑仍无法写入；'
                                      '请重试或联系服务商。'}
                return {'ok': True, 'reason': '已有有效授权，无需联网'}
            return install_document(layout, document)
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
    # Never expose URLs, credentials, HTTP bodies or raw exceptions.
    return {'ok': False, 'reason': reason + ' 新增发布保持暂停，已有数据保留。'}


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
