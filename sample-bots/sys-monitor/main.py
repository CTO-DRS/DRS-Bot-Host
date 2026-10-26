"""System Monitor - samples interpreter/host metrics and logs them.

A long-running service-style bot: every ``interval_seconds`` it logs one
reading with CPU-time deltas, resident memory, thread count and GC load.
Demonstrates a cooperative periodic loop with progress reporting.

All values come from the Python standard library only (os, resource, gc,
threading, time), so it runs unmodified inside the Android host.
"""

from drs_host.sdk import get_context


def _rss_bytes():
    """Resident memory in bytes, or None when the platform hides it."""
    try:
        import resource

        # Linux/Android: ru_maxrss is KiB.
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except Exception:  # pragma: no cover - non-POSIX fallback
        return None


def _fmt_bytes(total):
    if total is None:
        return "n/a"
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024 or unit == "GB":
            return "%.1f %s" % (total, unit)
        total /= 1024.0
    return "n/a"


def _process_times():
    try:
        import os

        times = os.times()
        return {"user": times.user, "system": times.system}
    except Exception:  # pragma: no cover - defensive
        return None


def _reading(times, user_delta, system_delta):
    import gc
    import threading

    parts = [
        "cpu(user %.3fs/sys %.3fs)" % (user_delta, system_delta),
        "rss %s" % _fmt_bytes(_rss_bytes()),
        "threads %d" % threading.active_count(),
        "gc objects %d" % len(gc.get_objects()),
    ]
    if times is not None:
        parts.insert(
            0,
            "total(user %.1fs/sys %.1fs)"
            % (times.get("user", 0.0), times.get("system", 0.0)),
        )
    return "sample: " + " | ".join(parts)


def main():
    ctx = get_context()
    if ctx is None:
        print("sys-monitor: no host context; one standalone sample then exit")
        print(_reading(_process_times(), 0.0, 0.0))
        return

    try:
        interval = float(ctx.config.get("interval_seconds", 5.0))
    except (TypeError, ValueError):
        interval = 5.0
    interval = max(1.0, min(interval, 3600.0))

    ctx.logger.info("sys-monitor started (interval %.1fs)" % interval)
    previous = _process_times()
    samples = 0
    while not ctx.should_stop:
        if ctx.sleep_or_stop(interval):
            break
        current = _process_times() or {}
        user_delta = 0.0
        system_delta = 0.0
        if previous is not None:
            user_delta = max(0.0, current.get("user", 0.0) - previous.get("user", 0.0))
            system_delta = max(0.0, current.get("system", 0.0) - previous.get("system", 0.0))
        previous = current
        samples += 1
        ctx.logger.info(_reading(current, user_delta, system_delta))
        ctx.set_progress(value=samples % 60, total=60, label="sampling")
    ctx.logger.info("sys-monitor stopped cleanly after %d samples" % samples)


main()
