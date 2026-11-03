"""Owned command trees; Windows children join a job before user code runs."""
import os
import signal
import subprocess
import time
from pathlib import Path

from .subprocess_text import hidden_window_options


class ProcessTree:
    def __init__(self, argv, **kwargs):
        self.job = None
        self.proc = None
        if os.name != 'nt':
            self.proc = subprocess.Popen(argv, start_new_session=True, **kwargs)
            return
        import ctypes as c
        from ctypes import wintypes as w

        class Basic(c.Structure):
            _fields_ = [('PerProcessUserTimeLimit', c.c_int64), ('PerJobUserTimeLimit', c.c_int64),
                        ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', c.c_size_t),
                        ('MaximumWorkingSetSize', c.c_size_t), ('ActiveProcessLimit', w.DWORD),
                        ('Affinity', c.c_size_t), ('PriorityClass', w.DWORD),
                        ('SchedulingClass', w.DWORD)]

        class IO(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount',
                         'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class Extended(c.Structure):
            _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO),
                        ('ProcessMemoryLimit', c.c_size_t), ('JobMemoryLimit', c.c_size_t),
                        ('PeakProcessMemoryUsed', c.c_size_t), ('PeakJobMemoryUsed', c.c_size_t)]

        self.kernel = k = c.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([c.c_void_p, w.LPCWSTR], w.HANDLE),
            'SetInformationJobObject': ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            'AssignProcessToJobObject': ([w.HANDLE, w.HANDLE], w.BOOL),
            'TerminateJobObject': ([w.HANDLE, w.UINT], w.BOOL),
            'QueryInformationJobObject': ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
            'CloseHandle': ([w.HANDLE], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(k, name)
            fn.argtypes, fn.restype = args, result
        self.job = k.CreateJobObjectW(None, None)
        if not self.job:
            raise c.WinError(c.get_last_error())
        try:
            limits = Extended()
            # KILL_ON_JOB_CLOSE (0x2000) owns normal exec children, while
            # BREAKAWAY_OK (0x0800) lets an explicitly detached browser escape
            # this request's job object and survive after /exec returns.
            limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x0800
            if not k.SetInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits)):
                raise c.WinError(c.get_last_error())
            # Popen closes the primary thread handle. Resume via a documented
            # Toolhelp thread snapshot only after the suspended process is owned.
            options = dict(kwargs)
            # CREATE_NO_WINDOW only.  DETACHED_PROCESS must NOT be used here:
            # a console program started without a console calls AllocConsole()
            # and shows a black window, which is exactly what customers see.
            window_options = hidden_window_options(argv, popen=True,
                                                   creationflags=0x4)
            hidden_stdin = window_options.pop("stdin", None)
            options.update(window_options)
            if hidden_stdin is not None:
                options.setdefault("stdin", hidden_stdin)
            self.proc = subprocess.Popen(argv, **options)
            if not k.AssignProcessToJobObject(self.job, int(self.proc._handle)):
                raise c.WinError(c.get_last_error())
            self._resume()
        except BaseException:
            if self.proc is not None:
                self.proc.kill()
                self.proc.wait(timeout=10)
            self.close()
            raise

    def _resume(self):
        import ctypes as c
        from ctypes import wintypes as w
        class ThreadEntry(c.Structure):
            _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('th32ThreadID', w.DWORD),
                        ('th32OwnerProcessID', w.DWORD), ('tpBasePri', w.LONG),
                        ('tpDeltaPri', w.LONG), ('dwFlags', w.DWORD)]
        k = self.kernel
        for name, args, result in (
            ('CreateToolhelp32Snapshot', [w.DWORD, w.DWORD], w.HANDLE),
            ('Thread32First', [w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            ('Thread32Next', [w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            ('OpenThread', [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            ('ResumeThread', [w.HANDLE], w.DWORD),
        ):
            getattr(k, name).argtypes, getattr(k, name).restype = args, result
        snapshot = k.CreateToolhelp32Snapshot(4, 0)
        if snapshot == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        try:
            entry = ThreadEntry()
            entry.dwSize = c.sizeof(entry)
            more = k.Thread32First(snapshot, c.byref(entry))
            while more:
                if entry.th32OwnerProcessID == self.proc.pid:
                    thread = k.OpenThread(2, False, entry.th32ThreadID)
                    if not thread:
                        raise c.WinError(c.get_last_error())
                    try:
                        if k.ResumeThread(thread) == 0xffffffff:
                            raise c.WinError(c.get_last_error())
                        return
                    finally:
                        k.CloseHandle(thread)
                more = k.Thread32Next(snapshot, c.byref(entry))
            raise RuntimeError('suspended process primary thread missing')
        finally:
            k.CloseHandle(snapshot)

    def close(self):
        if os.name == 'nt' and self.job:
            import ctypes as c
            from ctypes import wintypes as w
            # BASIC_ACCOUNTING_INFORMATION, including ActiveProcesses.
            class Accounting(c.Structure):
                _fields_ = [(n, c.c_int64) for n in ('TotalUserTime', 'TotalKernelTime',
                            'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime')] + [
                            (n, w.DWORD) for n in ('TotalPageFaultCount', 'TotalProcesses',
                                                   'ActiveProcesses', 'TotalTerminatedProcesses')]
            if not self.kernel.TerminateJobObject(self.job, 1):
                raise c.WinError(c.get_last_error())
            deadline = time.monotonic() + 10
            while True:
                info = Accounting()
                if not self.kernel.QueryInformationJobObject(self.job, 1, c.byref(info), c.sizeof(info), None):
                    raise c.WinError(c.get_last_error())
                if info.ActiveProcesses == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('command job still has active processes')
                time.sleep(.01)
            if not self.kernel.CloseHandle(self.job):
                raise c.WinError(c.get_last_error())
            self.job = None
        elif os.name != 'nt' and self.proc is not None:
            # The group remains owned even when the leader has already exited.
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.proc.wait(timeout=10)
            # SIGKILL delivery is asynchronous. Reaping the leader alone does
            # not establish that grandchildren have released their sockets.
            deadline = time.monotonic() + 10
            while self._group_running():
                if time.monotonic() >= deadline:
                    raise RuntimeError('command process group still running')
                time.sleep(.01)
        if self.proc is not None:
            self.proc.wait(timeout=10)

    def _group_running(self):
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(fields[2]) == self.proc.pid and fields[0] not in ('Z', 'X'):
                    return True
            except (FileNotFoundError, ProcessLookupError):
                continue
        return False
