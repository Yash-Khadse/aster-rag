"""Run once for bounded hosting, or poll a durable queue locally."""

import argparse
import time

from .jobs import run_one
from .main import app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        job_id = run_one(
            app.state.sessions, app.state.storage, app.state.pipeline, app.state.settings.lease_seconds
        )
        if args.once:
            break
        if job_id is None:
            time.sleep(2)


if __name__ == "__main__":
    main()
