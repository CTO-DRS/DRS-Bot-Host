"""Task Runner - executes a demo task list with progress, then completes.

A one-shot batch bot (``restart.policy = "never"``): it walks the task
names from its ``config`` section, reports a live progress bar after each
one, and finishes in the ``COMPLETED`` state. Stopping mid-run is safe and
clean because every wait goes through ``ctx.sleep_or_stop``.

Demonstrates: config reading, progress reporting, cooperative stopping
and a clean one-shot lifecycle. Standard library only.
"""

from drs_host.sdk import get_context


def main():
    ctx = get_context()
    if ctx is None:
        print("task-runner: no host context; standalone demo of 3 tasks")
        tasks = ["prepare", "scan", "report"]
        per_task = 0.5
        import time

        for index, task in enumerate(tasks, 1):
            print("[%d/%d] %s ... done" % (index, len(tasks), task))
            time.sleep(per_task)
        print("all tasks done")
        return

    raw_tasks = ctx.config.get("tasks") or []
    tasks = [str(task) for task in raw_tasks if str(task).strip()] or [
        "prepare",
        "scan",
        "report",
    ]
    try:
        per_task = float(ctx.config.get("per_task_seconds", 2.0))
    except (TypeError, ValueError):
        per_task = 2.0
    per_task = max(0.1, min(per_task, 600.0))

    ctx.logger.info(
        "task-runner started: %d task(s), %.1fs each" % (len(tasks), per_task)
    )
    for index, task in enumerate(tasks, 1):
        ctx.logger.info("[%d/%d] %s: started" % (index, len(tasks), task))
        # Sleep in short cooperative slices so a stop request lands fast.
        remaining = per_task
        while remaining > 0 and not ctx.should_stop:
            slice_seconds = min(0.25, remaining)
            if ctx.sleep_or_stop(slice_seconds):
                break
            remaining -= slice_seconds
        if ctx.should_stop:
            ctx.logger.info(
                "task-runner stopped at task %d/%d (%s)"
                % (index, len(tasks), task)
            )
            return
        ctx.logger.info("[%d/%d] %s: done" % (index, len(tasks), task))
        ctx.set_progress(value=index, total=len(tasks), label=task)
    ctx.logger.info("all tasks done - completed cleanly")


main()
