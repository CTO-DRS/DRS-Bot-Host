"""Config Demo Bot - reads ``bot.json`` -> ``config`` and reports progress.

Demonstrates the three SDK primitives most bots need:
``ctx.config``, ``ctx.logger`` and ``ctx.set_progress()``.
"""

from drs_host.sdk import get_context


def main():
    ctx = get_context()
    if ctx is None:
        print("config-demo: no host context; nothing to do")
        return

    interval = float(ctx.config.get("interval_seconds", 2.0))
    emit_count = int(ctx.config.get("emit_count", 3))
    message = ctx.config.get("message", "hello from config-demo")

    ctx.logger.info(f"config: message={message!r} interval={interval} emits={emit_count}")

    for index in range(emit_count):
        if ctx.should_stop:
            break
        ctx.logger.info(message)
        ctx.set_progress(value=index + 1, total=emit_count, label="emitting")
        ctx.sleep_or_stop(interval)

    ctx.logger.info("config-demo finished its run")
    ctx.set_progress(value=emit_count, total=emit_count, label="done")


main()
