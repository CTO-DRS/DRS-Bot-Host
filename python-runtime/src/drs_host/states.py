"""Bot lifecycle states, shared by the supervisor and the scheduler.

Extracted into its own module so both can import it without a circular
dependency (``supervisor`` -> ``scheduler`` -> ``supervisor``).
"""


class BotState:
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    BACKOFF = "BACKOFF"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    FORCE_STOPPED = "FORCE_STOPPED"

    TERMINAL = {STOPPED, COMPLETED, FAILED, FORCE_STOPPED}
