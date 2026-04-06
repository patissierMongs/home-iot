"""엔트리포인트 — `python -m home_iot` 또는 `home-iot-agent`."""
from __future__ import annotations

import asyncio
import logging

import structlog

from .agent import Agent
from .config import settings


def _configure_logging() -> None:
    logging.basicConfig(level=settings.log_level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
    )


async def _run() -> None:
    _configure_logging()
    agent = Agent()
    try:
        await agent.run()
    except KeyboardInterrupt:
        pass
    finally:
        await agent.aclose()


def run() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    run()
