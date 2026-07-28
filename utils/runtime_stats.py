"""Lightweight runtime metrics for the stats panel (no psutil required)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional, Tuple


# (wall_time, idle, total, last_percent) for system-wide CPU
_last_sys_cpu: Optional[Tuple[float, float, float, float]] = None


def process_thread_count() -> int:
    """Number of threads in this process (best-effort)."""
    try:
        if os.name == "nt":
            return max(1, (os.cpu_count() or 1))
        status = Path("/proc/self/status")
        if status.is_file():
            for line in status.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("Threads:"):
                    return max(1, int(line.split()[1]))
    except Exception:
        pass
    return max(1, (os.cpu_count() or 1))


def _read_proc_stat_idle_total() -> Optional[Tuple[float, float]]:
    try:
        line = Path("/proc/stat").read_text(encoding="utf-8", errors="replace").splitlines()[0]
        # cpu user nice system idle iowait irq softirq steal ...
        parts = line.split()
        if parts[0] != "cpu":
            return None
        nums = [float(x) for x in parts[1:]]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0.0)  # idle + iowait
        total = sum(nums)
        return idle, total
    except Exception:
        return None


def process_cpu_percent() -> float:
    """
    System-wide CPU busy % (0–100).

    Whisper runs as a child process (and often on GPU), so measuring only the
    Python parent stays near 0%. System load is what the user expects here.
    """
    global _last_sys_cpu
    sample = _read_proc_stat_idle_total()
    if not sample:
        return 0.0
    idle, total = sample
    now = time.time()
    if _last_sys_cpu is None:
        _last_sys_cpu = (now, idle, total, 0.0)
        return 0.0
    _prev_wall, prev_idle, prev_total, prev_pct = _last_sys_cpu
    dt_total = total - prev_total
    dt_idle = idle - prev_idle
    if dt_total <= 0:
        return prev_pct
    busy = max(0.0, min(100.0, (1.0 - (dt_idle / dt_total)) * 100.0))
    _last_sys_cpu = (now, idle, total, busy)
    return busy


def path_size_mb(path: Optional[str]) -> float:
    """Size of a file or total size of files under a directory, in MB."""
    if not path:
        return 0.0
    p = Path(path).expanduser()
    try:
        if p.is_file():
            return p.stat().st_size / (1024 * 1024)
        if p.is_dir():
            total = 0
            for root, _dirs, files in os.walk(p):
                for name in files:
                    try:
                        total += (Path(root) / name).stat().st_size
                    except OSError:
                        continue
            return total / (1024 * 1024)
    except OSError:
        return 0.0
    return 0.0


def dir_delta_mb(path: Optional[str], baseline_mb: float) -> float:
    """MB written under path since baseline snapshot."""
    current = path_size_mb(path)
    return max(0.0, current - (baseline_mb or 0.0))
