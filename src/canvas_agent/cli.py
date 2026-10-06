"""CLI entrypoints: once | run."""

from __future__ import annotations

import argparse
import logging
import sys

from canvas_agent.canvas.client import CanvasClient
from canvas_agent.config import Config
from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import ParleyAdvisor, StubAdvisor
from canvas_agent.logging_utils import setup_logging
from canvas_agent.models import AdvisorDecision
from canvas_agent.scheduler import FileLock, IntervalScheduler
from canvas_agent.storage.json_store import JsonFileStorage


def _build_orchestrator(config: Config) -> CycleOrchestrator:
    storage = JsonFileStorage(config.state_path)
    canvas = CanvasClient(
        config.canvas_base_url,
        config.canvas_token,
        config.course_id,
        config.topic_id,
    )
    if config.llm_api_key:
        advisor: ParleyAdvisor | StubAdvisor = ParleyAdvisor(
            config.llm_api_key,
            model=config.llm_model,
            base_url=config.llm_base_url,
        )
    else:
        logging.getLogger(__name__).warning(
            "PARLEY_API_KEY not set; using abstain-only stub advisor"
        )
        advisor = StubAdvisor(AdvisorDecision(action="abstain", rationale="no_llm_key"))
    return CycleOrchestrator(
        config=config, storage=storage, canvas=canvas, advisor=advisor
    )


def cmd_once(args: argparse.Namespace) -> int:
    config = Config.from_env(dry_run=True if args.dry_run else None)
    setup_logging(secrets=[config.canvas_token, config.llm_api_key or ""])
    logging.getLogger(__name__).info(
        "Starting single cycle dry_run=%s model=%s",
        config.dry_run,
        config.llm_model,
    )

    lock = FileLock(config.lock_path)
    if not lock.acquire():
        logging.getLogger(__name__).error("Could not acquire lock %s", config.lock_path)
        return 1
    try:
        orch = _build_orchestrator(config)
        try:
            result = orch.run_once()
        finally:
            orch.canvas.close()
    finally:
        lock.release()

    if result.error:
        return 1
    if result.skipped_reason and result.skipped_reason.startswith("stopped:"):
        return 2
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = Config.from_env(dry_run=True if args.dry_run else None)
    interval = args.interval_hours if args.interval_hours is not None else config.interval_hours
    setup_logging(secrets=[config.canvas_token, config.llm_api_key or ""])
    logging.getLogger(__name__).info(
        "Starting scheduler interval_hours=%s dry_run=%s model=%s",
        interval,
        config.dry_run,
        config.llm_model,
    )

    orch = _build_orchestrator(config)

    def run_cycle() -> object:
        return orch.run_once()

    scheduler = IntervalScheduler(
        run_cycle,
        interval_hours=interval,
        lock_path=config.lock_path,
    )
    try:
        return scheduler.run_forever()
    finally:
        orch.canvas.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canvas-agent",
        description="Autonomous Canvas discussion agent",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="Run a single cycle")
    once.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform the full cycle but never write to Canvas",
    )
    once.set_defaults(func=cmd_once)

    run = sub.add_parser("run", help="Run on an interval until stopped")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform cycles but never write to Canvas",
    )
    run.add_argument(
        "--interval-hours",
        type=float,
        default=None,
        help="Hours between cycles (default: 3)",
    )
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
