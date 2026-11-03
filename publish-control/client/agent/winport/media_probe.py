"""Bounded ISO BMFF header reader (MP4/MOV/M4V), no external executable.

Reads container-declared duration and sample-entry codec, NOT full decode health.
Malformed/fragmented files without a finite duration fail closed.
"""
import math
import struct
from pathlib import Path


def probe_mp4(path):
    path = Path(path)
    duration = None
    codecs = set()
    count = 0
    with path.open('rb') as fh:
        def boxes(start, end, depth=0):
            nonlocal duration, count
            if depth > 12:
                raise ValueError('box nesting too deep')
            pos = start
            while pos < end:
                count += 1
                if count > 100000 or end - pos < 8:
                    raise ValueError('invalid box table')
                fh.seek(pos)
                size, tag = struct.unpack('>I4s', fh.read(8))
                header = 8
                if size == 1:
                    size = struct.unpack('>Q', fh.read(8))[0]
                    header = 16
                elif size == 0:
                    size = end - pos
                if size < header or pos + size > end:
                    raise ValueError('box exceeds file')
                payload = pos + header
                if tag in (b'moov', b'trak', b'mdia', b'minf', b'stbl'):
                    boxes(payload, pos + size, depth + 1)
                elif tag == b'mvhd':
                    fh.seek(payload)
                    raw = fh.read(min(size - header, 32))
                    version = raw[0]
                    if version == 0 and len(raw) >= 20:
                        scale, ticks = struct.unpack('>II', raw[12:20])
                        if ticks == 0xffffffff:
                            raise ValueError('unknown duration')
                    elif version == 1 and len(raw) >= 32:
                        scale, ticks = struct.unpack('>IQ', raw[20:32])
                        if ticks == 0xffffffffffffffff:
                            raise ValueError('unknown duration')
                    else:
                        raise ValueError('unsupported movie header')
                    duration = ticks * 1000 / scale if scale else None
                elif tag == b'stsd':
                    fh.seek(payload)
                    raw = fh.read(min(size - header, 16))
                    if len(raw) >= 16 and struct.unpack('>I', raw[4:8])[0] == 1:
                        codec = raw[12:16].decode('ascii')
                        if codec in ('avc1', 'avc3', 'hvc1', 'hev1', 'av01', 'vp09', 'mp4v'):
                            codecs.add(codec)
                pos += size
        boxes(0, path.stat().st_size)
    if duration is None or not math.isfinite(duration) or duration <= 0 or not codecs:
        raise ValueError('no finite duration/video sample entry')
    return {'duration_ms': duration, 'encoding': ','.join(sorted(codecs)),
            'duration_known': True, 'encoding_known': True}
