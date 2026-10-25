"""DRS Bot Host runtime core.

Packages the bot manifest specification, the safe importer, the thread-per-bot
supervisor with restart policies, and the public SDK that bots use to talk to
the host. The same package runs in three places:

- inside the Android app via Chaquopy (bridge: ``drs_host.host_api``)
- on a desktop/CI environment via the CLI (``python -m drs_host.cli``)
- inside the pytest suite that verifies the core logic
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
