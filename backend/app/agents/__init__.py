import asyncio

import asyncpg

from app.agents import (
    authenticity_agent,
    consistency_agent,
    factcheck_agent,
    grammar_agent,
    novelty_agent,
)
from app.constants import AgentName, AgentStatus
from app.types import AgentResult
from app.utils.logger import get_logger

log = get_logger(__name__)


async def run_sanity_check(pool: asyncpg.Pool, paper_id: str) -> dict[str, AgentResult]:
    """Wave 1 — grammar + factcheck + novelty."""
    log.info("sanity_check: launching for paper=%s", paper_id)
    results = await asyncio.gather(
        grammar_agent.run(pool, paper_id),
        factcheck_agent.run(pool, paper_id),
        novelty_agent.run(pool, paper_id),
        return_exceptions=True,
    )
    return _make_output([AgentName.GRAMMAR, AgentName.FACTCHECK, AgentName.NOVELTY], results, "sanity_check")


async def run_fraud_check(pool: asyncpg.Pool, paper_id: str) -> dict[str, AgentResult]:
    """Wave 2 — consistency + authenticity."""
    log.info("fraud_check: launching for paper=%s", paper_id)
    results = await asyncio.gather(
        consistency_agent.run(pool, paper_id),
        authenticity_agent.run(pool, paper_id),
        return_exceptions=True,
    )
    return _make_output([AgentName.CONSISTENCY, AgentName.AUTHENTICITY], results, "fraud_check")


async def run_all_agents(pool: asyncpg.Pool, paper_id: str) -> dict[str, AgentResult]:
    """Runs both waves in parallel and merges results."""
    log.info("run_all_agents: launching both waves for paper=%s", paper_id)
    sanity, fraud = await asyncio.gather(
        run_sanity_check(pool, paper_id),
        run_fraud_check(pool, paper_id),
    )
    merged = {**sanity, **fraud}
    scores = {k: f"{v.score:.1f}" for k, v in merged.items()}
    log.info("run_all_agents: done paper=%s scores=%s", paper_id, scores)
    return merged


def _make_output(
    agent_names: list[AgentName],
    gather_results: tuple,
    wave: str,
) -> dict[str, AgentResult]:
    output: dict[str, AgentResult] = {}
    for agent_name, res in zip(agent_names, gather_results):
        if isinstance(res, BaseException):
            log.error("%s: %s raised unexpectedly — %s", wave, agent_name, res)
            output[agent_name] = AgentResult(
                agent_name=agent_name,
                score=50.0,
                status=AgentStatus.FAILED,
                error_msg=str(res),
            )
        else:
            output[agent_name] = res
    scores = {k: f"{v.score:.1f}" for k, v in output.items()}
    log.info("%s: done — %s", wave, scores)
    return output


__all__ = [
    "run_sanity_check",
    "run_fraud_check",
    "run_all_agents",
    "grammar_agent",
    "factcheck_agent",
    "novelty_agent",
    "consistency_agent",
    "authenticity_agent",
]
