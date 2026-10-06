"""Interval scheduler with graceful shutdown and file-lock overlap protection."""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class FileLock:
    """Simple exclusive lock using O_EXCL create."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self._fd, str(os.getpid()).encode("utf-8"))
            return True
        except FileExistsError:
            return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def __enter__(self) -> FileLock:
        if not self.acquire():
            raise RuntimeError(f"Another agent holds the lock: {self.path}")
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


class IntervalScheduler:
    def __init__(
        self,
        run_cycle: Callable[[], object],
        *,
        interval_hours: float = 3.0,
        lock_path: Path,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._run_cycle = run_cycle
        self._interval_seconds = max(60.0, interval_hours * 3600.0)
        self._lock_path = lock_path
        self._sleep = sleep_fn or time.sleep
        self._stop = False

    def request_stop(self, *_args: object) -> None:
        logger.info("Stop requested; will exit after current cycle boundary")
        self._stop = True

    def run_forever(self) -> int:
        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)

        with FileLock(self._lock_path):
            while not self._stop:
                result = self._run_cycle()
                stopped = getattr(result, "skipped_reason", None)
                if isinstance(stopped, str) and stopped.startswith("stopped:"):
                    logger.error("Agent stopped: %s", stopped)
                    return 2
                error = getattr(result, "error", None)
                # Check persisted stop via consecutive failures reflected in skipped_reason
                if self._stop:
                    break
                logger.info(
                    "Sleeping %.0f seconds until next cycle", self._interval_seconds
                )
                # Interruptible sleep
                remaining = self._interval_seconds
                while remaining > 0 and not self._stop:
                    step = min(1.0, remaining)
                    self._sleep(step)
                    remaining -= step
        return 0
