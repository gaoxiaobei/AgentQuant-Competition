"""Local worker for platform-owned baselines."""

import argparse
import logging
from time import sleep

from . import demo
from .contracts import RunError
from .jobs import JobStore, local_database

logger = logging.getLogger(__name__)


def run_once(jobs: JobStore) -> bool:
    claim = jobs.claim()
    if claim is None:
        return False
    try:
        outcome = demo.run(claim.spec)
    except Exception:
        logger.exception("Evaluation failed for run %s", claim.spec.run_id)
        outcome = RunError(code="EVALUATION_FAILED", message="示例评测失败，请查看 Worker 日志")
    if jobs.finish(claim, outcome):
        logger.info("Finished run %s", claim.spec.run_id)
    else:
        logger.warning("Run %s lost its lease", claim.spec.run_id)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AgentQuant local evaluation worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one task and exit.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    jobs = JobStore(local_database())
    if args.once:
        run_once(jobs)
        return
    logger.info("Listening for local evaluation jobs")
    try:
        while True:
            if not run_once(jobs):
                sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Worker stopped")


if __name__ == "__main__":
    main()
