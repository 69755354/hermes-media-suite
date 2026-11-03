#!/usr/bin/env python3
"""磁盘与存储 watchdog（2026-08-11 天行者定案，2026-09-05 修订）
根治「state.db 权限漂移 / 磁盘满 / 临时文件堆积 / 备份堆积」反复出现的问题。

每 30 分钟检查：
1. 磁盘用量（>85% 告警，>90% 自动清 /tmp 和缓存）
2. state.db 权限漂移（非 664 → 自动修复）
3. /tmp 大文件堆积（>50MB 且 >24h 的旧文件 → 清理）
4. ~/.hermes 缓存膨胀（>1GB → 清理旧媒体缓存）
5. client-backups 无条件只留 3 天（2026-09-05 修订：原在磁盘≥90%才触发，78%时不执行导致堆积6.6G）

超阈值写告警标记文件（DISK_DEGRADED），恢复后清除。
"""
import os
import shutil
import sys
import time

ALERT_FILE = "/tmp/disk_degraded"
LOG_FILE = "/tmp/disk_watchdog.log"
CHECK_INTERVAL = 1800  # 30 分钟

# 阈值
DISK_WARN_PCT = 75
DISK_CLEAN_PCT = 90
TMP_CLEAN_SIZE = 500 * 1024 * 1024  # /tmp 超 500MB 且文件>24h 才清
TMP_FILE_AGE = 24 * 3600
CACHE_CLEAN_SIZE = 1024 * 1024 * 1024  # cache 超 1GB 触发清理

# 关键文件（权限漂移自动修复）
CRITICAL_FILES = [
    os.path.expanduser("~/.hermes/state.db"),
    os.path.expanduser("~/.hermes/state.db-wal"),
    os.path.expanduser("~/.hermes/state.db-shm"),
]
CRITICAL_MODE = 0o664

def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts} {msg}\n")

def get_disk_pct(path: str = "/") -> float:
    """磁盘用量百分比"""
    try:
        usage = shutil.disk_usage(path)
        return usage.used / usage.total * 100
    except Exception:
        return 0.0

def fix_state_db_perms() -> bool:
    """修复 state.db 权限漂移，返回是否修过"""
    fixed = False
    for fp in CRITICAL_FILES:
        try:
            if os.path.exists(fp):
                mode = os.stat(fp).st_mode & 0o777
                if mode != CRITICAL_MODE:
                    os.chmod(fp, CRITICAL_MODE)
                    log(f"修复权限: {fp} {oct(mode)} -> {oct(CRITICAL_MODE)}")
                    fixed = True
        except Exception as e:
            log(f"权限修复失败 {fp}: {e}")
    return fixed

def clean_tmp() -> int:
    """清理 /tmp 超过阈值且过旧的临时文件，返回删除数"""
    removed = 0
    now = time.time()
    try:
        for name in os.listdir("/tmp"):
            fp = os.path.join("/tmp", name)
            try:
                if os.path.isfile(fp):
                    size = os.path.getsize(fp)
                    age = now - os.path.getmtime(fp)
                    if size > 50 * 1024 * 1024 and age > TMP_FILE_AGE:  # >50MB 且 >24h
                        os.remove(fp)
                        log(f"清理 /tmp 旧大文件: {name} ({size/1024/1024:.0f}MB)")
                        removed += 1
                elif os.path.isdir(fp):
                    # 目录只清 /tmp 下我们自己建的大目录（按名字前缀）
                    # 2026-08-21 补 patchtest：patch 工具测试副本（12G 攒了一夜没清，disk full 差点吞回复）
                    if name.startswith(("mingxi", "sync_to", "claude_remote", "patchtest")):
                        size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(fp) for f in fs)
                        if size > TMP_CLEAN_SIZE:
                            shutil.rmtree(fp, ignore_errors=True)
                            log(f"清理 /tmp 大目录: {name} ({size/1024/1024:.0f}MB)")
                            removed += 1
            except Exception:
                continue
    except Exception as e:
        log(f"清理 /tmp 失败: {e}")
    return removed

def clean_cache() -> int:
    """清理 ~/.hermes 缓存膨胀，返回删除数"""
    removed = 0
    cache_dirs = [
        os.path.expanduser("~/.hermes/cache"),
        os.path.expanduser("~/.hermes/audio_cache"),
    ]
    for cd in cache_dirs:
        try:
            if not os.path.isdir(cd):
                continue
            total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(cd) for f in fs)
            if total > CACHE_CLEAN_SIZE:
                now = time.time()
                for dp, _, fs in os.walk(cd):
                    for f in fs:
                        fp = os.path.join(dp, f)
                        try:
                            if now - os.path.getmtime(fp) > 7 * 86400:  # >7天
                                os.remove(fp)
                                removed += 1
                        except Exception:
                            continue
                log(f"清理缓存: {cd} 超过阈值 ({total/1024/1024:.0f}MB)")
        except Exception as e:
            log(f"清理缓存失败 {cd}: {e}")
    return removed

def clean_client_backups() -> int:
    """清理 client-backups 只留3天，无条件执行（2026-09-05 修订：原在磁盘≥90%才触发，78%时不执行导致堆积6.6G）"""
    removed = 0
    bp = os.path.expanduser("~/client-backups")
    if not os.path.isdir(bp):
        return 0
    now = time.time()
    keep = 3 * 86400
    for name in os.listdir(bp):
        fp = os.path.join(bp, name)
        try:
            if os.path.isdir(fp):
                age = now - os.path.getmtime(fp)
                if age > keep:
                    shutil.rmtree(fp, ignore_errors=True)
                    log(f"clean backup: {name}")
                    removed += 1
        except Exception as e:
            log(f"clean fail {name}: {e}")
    return removed

def main() -> None:
    log("disk_watchdog 启动")
    while True:
        alert = False
        # 0. 无条件清理：client-backups 只留3天（不管磁盘水位）
        clean_client_backups()
        # 1. 磁盘检查
        pct = get_disk_pct()
        if pct >= DISK_CLEAN_PCT:
            n1 = clean_tmp()
            n2 = clean_cache()
            log(f"磁盘 {pct:.0f}% ≥ {DISK_CLEAN_PCT}%，触发清理 (tmp={n1}, cache={n2})")
            alert = True
        elif pct >= DISK_WARN_PCT:
            log(f"磁盘 {pct:.0f}% ≥ {DISK_WARN_PCT}% 告警阈值")
            alert = True

        # 2. 权限修复
        if fix_state_db_perms():
            alert = False  # 已修复不告警

        # 3. 告警标记
        if alert:
            if not os.path.exists(ALERT_FILE):
                with open(ALERT_FILE, "w") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" disk={pct:.0f}%\n")
                log("已标记 DISK_DEGRADED")
        else:
            if os.path.exists(ALERT_FILE):
                os.remove(ALERT_FILE)
                log("磁盘状态恢复，DISK_DEGRADED 清除")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
