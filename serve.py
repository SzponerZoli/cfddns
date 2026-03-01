from __future__ import annotations

import os
import sys

from gunicorn.app.base import BaseApplication

from app import app as flask_app
from app import start_scheduler_once


class StandaloneApplication(BaseApplication):
    def __init__(self, application, options: dict | None = None):
        self.options = options or {}
        self.application = application
        super().__init__()

    def load_config(self):
        valid_options = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in valid_options.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


def main() -> int:
    start_scheduler_once()

    host = os.getenv("CFDDNS_HOST", "0.0.0.0")
    port = os.getenv("CFDDNS_PORT", "8080")
    bind_from_env = os.getenv("CFDDNS_BIND", "").strip()
    if os.getenv("CFDDNS_PORT"):
        bind = f"{host}:{port}"
    elif bind_from_env:
        bind = bind_from_env
    else:
        bind = f"{host}:{port}"
    workers = os.getenv("CFDDNS_WORKERS", "1")

    options = {
        "bind": bind,
        "workers": int(workers),
        "timeout": 120,
    }

    if len(sys.argv) > 1:
        sys.argv = [sys.argv[0], *sys.argv[1:]]

    StandaloneApplication(flask_app, options).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
