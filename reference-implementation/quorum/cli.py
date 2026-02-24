"""
Quorum CLI — Command-line interface.

Usage:
  quorum run --target <file> [--depth quick|standard|thorough] [--rubric <name>]
  quorum rubrics list
  quorum config init

First-run setup: if no API key is configured, quorum will prompt for one.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click
import yaml

from quorum.__init__ import __version__

logger = logging.getLogger("quorum")


# ──────────────────────────────────────────────────────────────────────────────
# Root group
# ──────────────────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(__version__, prog_name="quorum")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """
    Quorum — Multi-critic quality validation.

    Evaluates artifacts (configs, research, code) against domain-specific
    rubrics using specialized critics, each required to provide grounded evidence.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
    )


# ──────────────────────────────────────────────────────────────────────────────
# quorum run
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("run")
@click.option(
    "--target", "-t",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to the artifact file to validate",
)
@click.option(
    "--depth", "-d",
    default="quick",
    type=click.Choice(["quick", "standard", "thorough"], case_sensitive=False),
    show_default=True,
    help="Validation depth profile",
)
@click.option(
    "--rubric", "-r",
    default=None,
    help="Rubric name (built-in) or path to a JSON rubric file. Auto-detected if omitted.",
)
@click.option(
    "--config", "-c",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a custom YAML config file (overrides depth profile)",
)
@click.option(
    "--output-dir", "-o",
    default=None,
    type=click.Path(path_type=Path),
    help="Directory for run outputs (default: ./quorum-runs/)",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Print full evidence for all findings (not just CRITICAL/HIGH)",
)
def run_cmd(
    target: Path,
    depth: str,
    rubric: str | None,
    config: Path | None,
    output_dir: Path | None,
    verbose: bool,
) -> None:
    """
    Validate an artifact against a rubric.

    Examples:

      quorum run --target my-config.yaml

      quorum run --target research.md --depth standard --rubric research-synthesis

      quorum run --target agent.yaml --rubric agent-config --depth thorough
    """
    from quorum.output import print_verdict, print_error, print_warning

    # Check for API keys before doing any work
    if not _has_api_key():
        _first_run_setup()
        if not _has_api_key():
            print_error(
                "No API key configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
                "or another LiteLLM-supported provider key in your environment."
            )
            sys.exit(1)

    try:
        from quorum.config import load_config, QuorumConfig
        from quorum.pipeline import run_validation

        # Load config
        if config:
            quorum_config = QuorumConfig.from_yaml(config)
        else:
            quorum_config = load_config(depth=depth)

        click.echo(
            f"Running Quorum ({quorum_config.depth_profile} depth, "
            f"critics: {', '.join(quorum_config.critics)}) ...",
            err=True,
        )

        verdict, run_dir = run_validation(
            target_path=target,
            depth=depth,
            rubric_name=rubric,
            config=quorum_config,
            runs_dir=output_dir or Path("quorum-runs"),
        )

        print_verdict(verdict, run_dir=run_dir, verbose=verbose)

        # Exit with non-zero code if the artifact needs work
        if verdict.is_actionable:
            sys.exit(2)  # 2 = validation failed (not a crash)

    except FileNotFoundError as e:
        print_error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.debug("Unexpected error", exc_info=True)
        from quorum.output import print_error
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# quorum rubrics
# ──────────────────────────────────────────────────────────────────────────────

@cli.group("rubrics")
def rubrics_group() -> None:
    """Manage rubrics."""


@rubrics_group.command("list")
def rubrics_list() -> None:
    """List all available built-in rubrics."""
    from quorum.rubrics.loader import RubricLoader
    from quorum.output import print_rubric_list

    loader = RubricLoader()
    names = loader.list_builtin()

    if names:
        print_rubric_list(names)
    else:
        click.echo("No built-in rubrics found. Have you installed the package correctly?")


@rubrics_group.command("show")
@click.argument("name")
def rubrics_show(name: str) -> None:
    """Show criteria for a rubric."""
    from quorum.rubrics.loader import RubricLoader
    from quorum.output import print_error

    loader = RubricLoader()
    try:
        rubric = loader.load(name)
    except FileNotFoundError as e:
        print_error(str(e))
        sys.exit(1)

    click.echo(f"\n{rubric.name} (v{rubric.version})")
    click.echo(f"Domain: {rubric.domain}")
    if rubric.description:
        click.echo(f"{rubric.description}")
    click.echo()
    click.echo(f"{'ID':<12} {'Severity':<10} {'Criterion'}")
    click.echo("─" * 80)
    for c in rubric.criteria:
        click.echo(f"{c.id:<12} {c.severity.value:<10} {c.criterion[:60]}")
    click.echo()


# ──────────────────────────────────────────────────────────────────────────────
# quorum config
# ──────────────────────────────────────────────────────────────────────────────

@cli.group("config")
def config_group() -> None:
    """Manage Quorum configuration."""


@config_group.command("init")
def config_init() -> None:
    """Interactive first-run setup — creates quorum-config.yaml."""
    _first_run_setup(force=True)


# ──────────────────────────────────────────────────────────────────────────────
# First-run helpers
# ──────────────────────────────────────────────────────────────────────────────

def _has_api_key() -> bool:
    """Check if any LiteLLM-supported API key is configured in the environment."""
    provider_keys = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "MISTRAL_API_KEY",
        "GROQ_API_KEY",
        "COHERE_API_KEY",
        "AZURE_API_KEY",
        "GEMINI_API_KEY",
        "TOGETHER_API_KEY",
    ]
    return any(os.environ.get(k) for k in provider_keys)


def _first_run_setup(force: bool = False) -> None:
    """
    Interactive first-run configuration.

    Asks two questions:
    1. Which model tier to use (determines tier_1 and tier_2)
    2. Default depth profile

    Writes a quorum-config.yaml to cwd.
    """
    config_path = Path("quorum-config.yaml")
    if config_path.exists() and not force:
        return  # Already configured

    click.echo()
    click.echo("Welcome to Quorum! Let's set up your configuration.")
    click.echo()

    # Question 1: Model preference
    click.echo("Which LLM provider do you want to use?")
    click.echo("  1) Anthropic (Claude) — set ANTHROPIC_API_KEY")
    click.echo("  2) OpenAI (GPT-4)    — set OPENAI_API_KEY")
    click.echo("  3) Other (I'll configure manually)")
    click.echo()

    provider_choice = click.prompt(
        "Provider", type=click.Choice(["1", "2", "3"]), default="1"
    )

    if provider_choice == "1":
        tier_1 = "anthropic/claude-opus-4-0"
        tier_2 = "anthropic/claude-sonnet-4-20250514"
        key_var = "ANTHROPIC_API_KEY"
    elif provider_choice == "2":
        tier_1 = "gpt-4o"
        tier_2 = "gpt-4o-mini"
        key_var = "OPENAI_API_KEY"
    else:
        tier_1 = click.prompt("Tier 1 model name (strong model)", default="anthropic/claude-opus-4-0")
        tier_2 = click.prompt("Tier 2 model name (efficient model)", default="anthropic/claude-sonnet-4-20250514")
        key_var = None

    if key_var and not os.environ.get(key_var):
        api_key = click.prompt(
            f"Paste your {key_var} (leave blank to set it yourself later)",
            default="",
            hide_input=True,
        )
        if api_key:
            os.environ[key_var] = api_key
            click.echo(f"  ✓ {key_var} saved to environment for this session")
            click.echo(f"  (Add 'export {key_var}=...' to your shell profile to persist it)")

    # Question 2: Default depth
    click.echo()
    depth_choice = click.prompt(
        "Default depth profile",
        type=click.Choice(["quick", "standard", "thorough"]),
        default="quick",
    )

    # Write config
    config_data = {
        "critics": ["correctness", "completeness"],
        "model_tier1": tier_1,
        "model_tier2": tier_2,
        "max_fix_loops": 0,
        "depth_profile": depth_choice,
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)

    click.echo()
    click.echo(f"✓ Configuration written to {config_path}")
    click.echo(f"  Run: quorum run --target <your-file>")
    click.echo()
