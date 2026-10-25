"""Echo Bot - a minimal DRS Bot Host sample.

Prints a heartbeat once per second until the host asks it to stop.
Runs standalone too (outside the host) for quick manual testing.
"""

from drs_host.sdk import get_context


def main():
    ctx = get_context()
    if ctx is None:
        print("echo-bot: no host context; standalone run for 5 seconds")
        import time

        for i in range(5):
            print(f"standalone heartbeat #{i}")
            time.sleep(1)
        return

    ctx.logger.info("echo-bot started")
    counter = 0
    while not ctx.should_stop:
        ctx.logger.info(f"heartbeat #{counter}")
        ctx.set_progress(value=counter % 60, total=60, label="beating")
        counter += 1
        ctx.sleep_or_stop(1.0)
    ctx.logger.info(f"echo-bot stopped cleanly after {counter} beats")


main()
