"""Approval-to-local-bytes binding. No media is uploaded by these functions."""

import stat
from pathlib import Path

from .errors import GateRed
from .hashing import is_hex
from .idempotency import material_fingerprint
from .secure_io import sha256_file, secure_stat


def validate_local_content(plan, media=None):
    piece = plan.get('piece') or {}
    expected = (plan.get('compliance') or {}).get('content_hash')
    if expected != material_fingerprint(piece, account_id=plan.get('account_id', '')):
        raise GateRed('\u5185\u5bb9\u5df2\u53d8\u5316\u6216\u5ba1\u6279\u6458\u8981\u4e3a\u65e7\u683c\u5f0f\uff1b\u91cd\u65b0\u751f\u6210\u6e05\u5355\u5e76\u786e\u8ba4')
    if media is not None:
        if not is_hex(piece.get('sha256'), 64) or sha256_file(media) != piece['sha256']:
            raise GateRed('\u5b9e\u9645\u89c6\u9891\u5b57\u8282\u4e0e\u5ba1\u6279 SHA256 \u4e0d\u4e00\u81f4')
    covers = {k: v for k, v in (piece.get('covers') or {}).items() if v}
    digests = piece.get('cover_sha256') or {}
    if set(covers) != set(digests) or set(covers) - {'vertical', 'horizontal'}:
        raise GateRed('\u5c01\u9762\u987b\u9010\u9879\u63d0\u4f9b cover_sha256\uff0c\u4e14\u4ec5\u652f\u6301 vertical/horizontal')
    for kind, value in covers.items():
        path = Path(value)
        if not path.is_absolute():
            raise GateRed('\u5c01\u9762\u987b\u4e3a\u5b58\u5728\u7684\u7edd\u5bf9\u6587\u4ef6\u8def\u5f84\uff1a' + str(path))
        try:
            st = secure_stat(path)
        except OSError:
            raise GateRed('\u5c01\u9762\u987b\u4e3a\u5b58\u5728\u7684\u7edd\u5bf9\u6587\u4ef6\u8def\u5f84\uff1a' + str(path))
        if not stat.S_ISREG(st.st_mode):
            raise GateRed('\u5c01\u9762\u987b\u4e3a\u5b58\u5728\u7684\u7edd\u5bf9\u6587\u4ef6\u8def\u5f84\uff1a' + str(path))
        if not is_hex(digests[kind], 64) or sha256_file(path) != digests[kind]:
            raise GateRed('\u5c01\u9762\u5b57\u8282\u4e0e\u5ba1\u6279\u6458\u8981\u4e0d\u4e00\u81f4\uff1a' + kind)
    return True
