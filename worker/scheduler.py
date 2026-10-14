"""Entry point.  `python -m worker.scheduler --once` for a single run (what launchd calls),
`python -m worker.scheduler` to loop every N hours in the foreground."""
import argparse
import logging
import time

from . import llm
from .db import DB
from .pipeline import run_once


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every-hours", type=float, default=3)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("JobSpy").setLevel(logging.WARNING)

    db = DB()
    llm.use_db(db)
    while True:
        print(run_once(db))
        if args.once:
            return
        time.sleep(args.every_hours * 3600)


if __name__ == "__main__":
    main()
