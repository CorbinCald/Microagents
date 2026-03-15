import argparse
import asyncio
import logging
import os
import sys

import yaml

from assembler import assemble_project
from logger import setup_logging
from microagent import dispatch_all
from orchestrator import generate_skeleton


def load_config(config_path: str = "config.yaml") -> dict:
    """Load and validate config.yaml."""
    if not os.path.exists(config_path):
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    key_env = config["api"]["key_env"]
    if not os.environ.get(key_env):
        print(f"Error: environment variable {key_env} is not set", file=sys.stderr)
        sys.exit(1)

    return config


async def run_pipeline(description: str, config: dict, log_file: str) -> None:
    """Run the full generation pipeline."""
    log = logging.getLogger("microagents")

    # Stage 2+3: Generate and parse skeleton
    file_specs, task_specs = generate_skeleton(description, config)

    # Stage 4+4B: Dispatch microagent tasks in parallel
    results = await dispatch_all(task_specs, config)

    succeeded = sum(1 for r in results.values() if r.status == "ok")
    total = len(results)
    log.info(f"{succeeded}/{total} tasks succeeded")

    # Stage 5+6: Assemble and write output
    log.info("Assembling files...")
    output_path = assemble_project(
        file_specs, results, task_specs, description, config, log_file
    )

    # Stage 7: Final summary
    log.info(
        f"Generated {len(file_specs)} files, {succeeded}/{total} tasks succeeded. "
        f"Output: ./{output_path}/"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a codebase from a natural-language project description"
    )
    parser.add_argument("description", help="Natural-language project description")
    args = parser.parse_args()

    config = load_config()
    _logger, log_file = setup_logging(config)

    asyncio.run(run_pipeline(args.description, config, log_file))


if __name__ == "__main__":
    main()
