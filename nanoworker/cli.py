"""CLI entry point for nanoworker."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

app = typer.Typer(name="nanoworker", help="Lightweight worker agent for multi-agent orchestration.")


# Skills directory: relative to this package
SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _run_async(coro):
    """Run an async function synchronously."""
    return asyncio.run(coro)


@app.command()
def worker(
    name: str = typer.Argument(help="Worker name (must be defined in config)"),
    message: str = typer.Argument(help="Task message for the worker"),
    workspace: str = typer.Option(..., "--workspace", "-w", help="Working directory for the worker"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model from config"),
    max_iterations: Optional[int] = typer.Option(None, "--max-iterations", help="Override max iterations"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
) -> None:
    """Run a named worker to execute a task."""
    # Configure logging: stderr only, no stdout pollution
    logger.remove()
    if verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO")

    from nanoworker.config import load_config
    from nanoworker.llm import setup_provider_env
    from nanoworker.prompt import build_system_prompt
    from nanoworker.runner import output_result, run_worker
    from nanoworker.tools import get_tools_for_role

    # 1. Load config
    config = load_config()

    # 2. Look up worker definition
    worker_def = config.workers.get(name)
    if worker_def is None:
        logger.error(f"Worker '{name}' not found in config. Available: {list(config.workers.keys())}")
        raise typer.Exit(code=1)

    # 3. Resolve parameters (CLI overrides config)
    resolved_model = model or worker_def.model
    resolved_max_iter = max_iterations or worker_def.max_iterations
    resolved_workspace = str(Path(workspace).resolve())

    logger.info(f"Worker: {name} | Role: {worker_def.role} | Model: {resolved_model}")
    logger.info(f"Workspace: {resolved_workspace}")

    # 4. Setup LLM provider environment
    setup_provider_env(config, resolved_model)

    # 5. Build tools for role
    tools = get_tools_for_role(worker_def.role, resolved_workspace)

    # 6. Build system prompt with skills
    system_prompt = build_system_prompt(
        worker_name=name,
        role=worker_def.role,
        workspace=resolved_workspace,
        skills_dir=SKILLS_DIR,
        skill_names=worker_def.skills,
    )

    logger.debug(f"System prompt ({len(system_prompt)} chars)")

    # 7. Run the agent loop
    result = _run_async(
        run_worker(
            model=resolved_model,
            system_prompt=system_prompt,
            task=message,
            tools=tools,
            max_iterations=resolved_max_iter,
        )
    )

    # 8. Output result
    output_result(result)

    raise typer.Exit(code=0 if result.success else 1)


if __name__ == "__main__":
    app()
