"""Autostart + crash self-recovery wiring.

Route 1 (recommended, usually no admin): Task Scheduler, onlogon trigger with
"restart on failure" -- the closest analogue to launchd RunAtLoad+KeepAlive.
Route 2 (degrade): HKCU\\...\\Run registry value, no crash recovery.
Route 3 (needs admin): a real Windows service.

This module BUILDS the exact commands/XML; executing them is a real-machine
item, and they are printed for static review.
"""

from __future__ import annotations

import os
from pathlib import Path

from .version import VENDOR

TASK_NAME = f"{VENDOR}\\Agent"
TUNNEL_TASK_NAME = f"{VENDOR}\\Tunnel"


def build_schtasks_create(task_name, program, arguments, *, run_level="LIMITED",
                          restart_minutes=1, delay="PT30S") -> list:
    """schtasks /create /sc onlogon (current user, usually no admin needed)."""
    return [
        "schtasks", "/create", "/f",
        "/tn", task_name,
        "/sc", "onlogon",
        "/delay", delay,
        "/rl", run_level,
        "/tr", f'"{program}" {arguments}',
    ]


def build_schtasks_delete(task_name) -> list:
    return ["schtasks", "/delete", "/f", "/tn", task_name]


def build_schtasks_run(task_name) -> list:
    return ["schtasks", "/run", "/tn", task_name]


def build_registry_run(value_name, command) -> dict:
    return {
        "key": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        "value_name": value_name,
        "command": command,
    }


def task_xml(task_name, program, arguments, *, user_id=r"%USERDOMAIN%\%USERNAME%",
             restart_minutes=1, interval_minutes=5) -> str:
    """Task Scheduler XML: onlogon trigger + restart-on-failure + 5-minute
    repetition (launchd StartInterval=300 parity) + throttle delay 30s."""
    # NOTE: emit UTF-8 here; schtasks /create /xml requires UTF-16LE with BOM,
    # so callers convert before importing.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{VENDOR} agent autostart (onlogon + restart on failure)</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user_id}</UserId>
      <Delay>PT30S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user_id}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT{restart_minutes}M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{program}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def wake_task_xml(task_name, program, arguments, at_time="06:55",
                  user_id=r"%USERDOMAIN%\\%USERNAME%") -> str:
    """Daily task with WakeToRun=True: brings the PC back from standby so the
    queue can publish at the scheduled point. Running it is idempotent -- the
    launcher returns at once when the agent is already resident."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{VENDOR} wake timer ({at_time}) for scheduled publishing</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{at_time}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user_id}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{program}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


WAKE_TIMES = ("06:55", "10:55", "16:55", "19:55")


def plan_wake_tasks(layout, launcher_command) -> dict:
    """Four daily wake timers, one just before each natural publish window."""
    python = layout.runtime / "python.exe"
    agent = layout.program / "agent" / "winport" / "daemon.py"
    tasks = []
    for index, at_time in enumerate(WAKE_TIMES, start=1):
        name = f"{TASK_NAME}_wake{index}"
        tasks.append({
            "task_name": name,
            "at": at_time,
            "task_xml": wake_task_xml(name, str(python), f'"{agent}"', at_time),
        })
    return {"tasks": tasks, "launcher": str(launcher_command)}


def plan_autostart(layout, launcher_command) -> dict:
    """Return the concrete install plan without executing anything."""
    python = layout.runtime / "python.exe"
    agent = layout.program / "agent" / "winport" / "daemon.py"
    return {
        "task_name": TASK_NAME,
        "schtasks_create": build_schtasks_create(
            TASK_NAME, str(launcher_command), "--agent"),
        "schtasks_run_now": build_schtasks_run(TASK_NAME),
        "task_xml": task_xml(TASK_NAME, str(python), f'"{agent}"'),
        "registry_fallback": build_registry_run(
            f"{VENDOR}Agent", f'"{launcher_command}" --agent'),
        "notes": "Route 1 task is the default. Execution is a real-machine item.",
    }
