# SPDX-License-Identifier: MIT
# Copyright 2026 SharedIntellect — https://github.com/SharedIntellect/quorum

"""
Supervisor Agent — Classifies artifact domain and selects the critic panel.

The Supervisor:
1. Reads the artifact and determines its domain (code, config, research, docs, ops)
2. Selects the appropriate critics for the depth profile
3. Dispatches critics sequentially (MVP; parallel in future versions)
4. Hands results to the Aggregator
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quorum.config import QuorumConfig
from quorum.critics.base import BaseCritic
from quorum.critics.completeness import CompletenessCritic
from quorum.critics.correctness import CorrectnessCritic
from quorum.models import CriticResult, Rubric
from quorum.providers.base import BaseProvider

logger = logging.getLogger(__name__)


# Map critic names → critic classes
CRITIC_REGISTRY: dict[str, type[BaseCritic]] = {
    "correctness": CorrectnessCritic,
    "completeness": CompletenessCritic,
    # security, architecture, delegation would be added here in future phases
}


class SupervisorAgent:
    """
    Orchestrates the validation pipeline.

    Responsibilities:
    - Classify artifact domain (used for rubric selection hints)
    - Instantiate and run critics from the config's critic list
    - Return list of CriticResults for the Aggregator to process
    """

    def __init__(self, provider: BaseProvider, config: QuorumConfig):
        self.provider = provider
        self.config = config

    def classify_domain(self, artifact_text: str, artifact_path: str) -> str:
        """
        Quickly classify the artifact's domain from its path and content.

        Returns one of: code, config, research, docs, ops, unknown
        """
        path = Path(artifact_path)
        ext = path.suffix.lower()

        # Path-based heuristics (cheap and reliable)
        if ext in (".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c"):
            return "code"
        if ext in (".yaml", ".yml", ".json", ".toml", ".ini", ".env"):
            return "config"
        if ext in (".md", ".rst", ".txt"):
            # Disambiguate between research and generic docs by content signals
            text_lower = artifact_text.lower()
            research_signals = [
                "abstract", "methodology", "findings", "hypothesis",
                "literature", "citation", "et al.", "study", "results",
            ]
            if sum(1 for s in research_signals if s in text_lower) >= 3:
                return "research"
            return "docs"

        return "unknown"

    def build_critics(self) -> list[BaseCritic]:
        """
        Instantiate critics from the config's critic list.

        Critics not yet implemented are skipped with a warning.
        """
        critics: list[BaseCritic] = []
        for name in self.config.critics:
            cls = CRITIC_REGISTRY.get(name)
            if cls is None:
                logger.warning(
                    "Critic '%s' is not yet implemented — skipping. "
                    "Available: %s",
                    name, list(CRITIC_REGISTRY.keys()),
                )
                continue
            critics.append(cls(provider=self.provider, config=self.config))

        if not critics:
            raise RuntimeError(
                f"No valid critics could be instantiated from config: {self.config.critics}. "
                f"Available: {list(CRITIC_REGISTRY.keys())}"
            )

        return critics

    def run(
        self,
        artifact_text: str,
        artifact_path: str,
        rubric: Rubric,
        extra_context: dict[str, Any] | None = None,
    ) -> list[CriticResult]:
        """
        Run all critics against the artifact.

        Args:
            artifact_text: Full text of the artifact
            artifact_path: File path (used for domain classification)
            rubric:        Rubric to evaluate against
            extra_context: Optional context injected into critic prompts

        Returns:
            List of CriticResult, one per critic that ran successfully
        """
        domain = self.classify_domain(artifact_text, artifact_path)
        logger.info(
            "Supervisor: artifact='%s' domain='%s' depth='%s' critics=%s",
            artifact_path, domain, self.config.depth_profile, self.config.critics,
        )

        critics = self.build_critics()
        results: list[CriticResult] = []

        for critic in critics:
            logger.info("Running critic: %s", critic.name)
            try:
                result = critic.evaluate(
                    artifact_text=artifact_text,
                    rubric=rubric,
                    extra_context=extra_context,
                )
                results.append(result)
                logger.info(
                    "Critic %s: %d findings (confidence=%.2f)",
                    critic.name, len(result.findings), result.confidence,
                )
            except Exception as e:
                logger.error("Critic %s crashed: %s", critic.name, e)
                # Append a skipped result so the Aggregator knows
                results.append(
                    CriticResult(
                        critic_name=critic.name,
                        findings=[],
                        confidence=0.0,
                        runtime_ms=0,
                        skipped=True,
                        skip_reason=str(e),
                    )
                )

        return results
