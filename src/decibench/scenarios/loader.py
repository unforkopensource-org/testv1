"""Scenario loader — load, validate, and expand YAML test scenarios."""

from __future__ import annotations

import logging
from importlib import resources
from typing import TYPE_CHECKING

import yaml
from pydantic import ValidationError

from decibench.models import Persona, Scenario

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# Built-in suite directories
_BUILTIN_SUITES_PKG = "decibench.scenarios.suites"


class ScenarioLoader:
    """Load and validate test scenarios from YAML files."""

    def __init__(self, custom_dir: Path | None = None) -> None:
        self._custom_dir = custom_dir

    def load_suite(self, suite_name: str) -> list[Scenario]:
        """Load all scenarios from a named suite.

        Looks in:
        1. Custom directory (if configured)
        2. Built-in suites bundled with decibench
        3. Composite suites (full = quick + standard + acoustic + adversarial)
        """
        # Handle composite 'full' suite
        if suite_name == "full":
            return self._load_full_suite()

        scenarios: list[Scenario] = []

        # Try custom directory first
        if self._custom_dir:
            suite_dir = self._custom_dir / suite_name
            if suite_dir.is_dir():
                scenarios = self._load_directory(suite_dir)
                if scenarios:
                    logger.info("Loaded %d scenarios from %s", len(scenarios), suite_dir)
                    return scenarios

        # Try built-in suites
        try:
            suite_ref = resources.files(_BUILTIN_SUITES_PKG).joinpath(suite_name)
            if suite_ref.is_dir():
                scenarios = self._load_from_package(suite_name)
        except (TypeError, FileNotFoundError):
            pass

        if not scenarios:
            logger.warning("Suite '%s' not found, generating default scenarios", suite_name)
            scenarios = self._generate_default_suite(suite_name)

        logger.info("Loaded %d scenarios for suite '%s'", len(scenarios), suite_name)
        return scenarios

    def _load_full_suite(self) -> list[Scenario]:
        """Load the full suite: quick + standard + acoustic + adversarial."""
        seen_ids: set[str] = set()
        all_scenarios: list[Scenario] = []

        for sub_suite in ("quick", "standard", "acoustic", "adversarial"):
            for scenario in self.load_suite(sub_suite):
                if scenario.id not in seen_ids:
                    seen_ids.add(scenario.id)
                    all_scenarios.append(scenario)

        logger.info("Full suite: %d scenarios", len(all_scenarios))
        return all_scenarios

    def load_file(self, path: Path) -> Scenario:
        """Load and validate a single scenario YAML file."""
        with open(path) as f:
            raw = yaml.safe_load(f)

        try:
            return Scenario.model_validate(raw)
        except ValidationError as e:
            msg = f"Invalid scenario {path}: {e}"
            raise ValueError(msg) from e

    def validate(self, scenario: Scenario) -> list[str]:
        """Validate a scenario and return any issues found."""
        issues: list[str] = []

        if not scenario.id:
            issues.append("Scenario missing 'id' field")

        if scenario.mode == "scripted" and not scenario.conversation:
            issues.append("Scripted scenario has no conversation turns")

        if scenario.mode == "adaptive" and not scenario.goal:
            issues.append("Adaptive scenario has no goal")

        # Check conversation structure
        for i, turn in enumerate(scenario.conversation):
            if turn.role == "caller" and not turn.text:
                issues.append(f"Turn {i}: caller turn missing text")
            if turn.role == "agent" and not turn.expect:
                issues.append(f"Turn {i}: agent turn missing expectations (optional but recommended)")

        return issues

    def expand_variants(
        self,
        scenarios: list[Scenario],
        noise_levels: list[str] | None = None,
        accents: list[str] | None = None,
        speeds: list[float] | None = None,
    ) -> list[Scenario]:
        """Expand scenarios across noise, accent, and speed variants.

        Cross-product expansion: 10 scenarios x 3 noise x 2 accents = 60 runs.
        """
        expanded: list[Scenario] = []

        for scenario in scenarios:
            # Use overrides or scenario's own variants or defaults
            noises = noise_levels or scenario.variants.noise_levels
            accs = accents or scenario.variants.accents
            spds = speeds or scenario.variants.speeds

            for noise in noises:
                for accent in accs:
                    for speed in spds:
                        variant = scenario.model_copy(deep=True)
                        variant_suffix = f"-{noise}-{accent}-{speed}x"
                        variant.id = f"{scenario.id}{variant_suffix}"
                        variant.persona.background_noise = noise
                        variant.persona.accent = accent
                        variant.persona.speaking_speed = speed
                        variant.metadata["variant_of"] = scenario.id
                        variant.metadata["noise"] = noise
                        variant.metadata["accent"] = accent
                        variant.metadata["speed"] = speed
                        expanded.append(variant)

        return expanded

    def _load_directory(self, directory: Path) -> list[Scenario]:
        """Load all YAML scenarios from a directory."""
        scenarios: list[Scenario] = []
        for path in sorted(directory.glob("*.yaml")):
            try:
                scenario = self.load_file(path)
                scenarios.append(scenario)
            except (ValueError, yaml.YAMLError) as e:
                logger.warning("Skipping invalid scenario %s: %s", path, e)
        return scenarios

    def _load_from_package(self, suite_name: str) -> list[Scenario]:
        """Load scenarios from bundled package data."""
        scenarios: list[Scenario] = []
        try:
            suite_dir = resources.files(_BUILTIN_SUITES_PKG).joinpath(suite_name)
            for item in suite_dir.iterdir():
                if str(item).endswith(".yaml"):
                    content = item.read_text(encoding="utf-8")
                    raw = yaml.safe_load(content)
                    scenarios.append(Scenario.model_validate(raw))
        except Exception as e:
            logger.debug("Could not load bundled suite '%s': %s", suite_name, e)
        return scenarios

    @staticmethod
    def _generate_default_suite(suite_name: str) -> list[Scenario]:
        """Generate default scenarios when no suite files exist."""
        if suite_name == "quick":
            return _generate_quick_suite()
        if suite_name == "standard":
            return _generate_quick_suite() + _generate_extended_scenarios()
        return _generate_quick_suite()


def _generate_quick_suite() -> list[Scenario]:
    """Generate the 10-scenario quick suite programmatically."""
    from decibench.models import ConversationTurn, SuccessCriterion, ToolMock, TurnExpectation

    scenarios = [
        Scenario(
            id="quick-greeting-001",
            description="Basic greeting and AI disclosure",
            conversation=[
                ConversationTurn(role="caller", text="Hello, is anyone there?"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        intent="greeting",
                        must_include=["hello", "help"],
                        max_latency_ms=800,
                    ),
                ),
            ],
            success_criteria=[
                SuccessCriterion(type="compliance", description="AI disclosure in greeting"),
                SuccessCriterion(type="latency", p95_max_ms=1500),
            ],
        ),
        Scenario(
            id="quick-booking-002",
            description="Appointment scheduling — happy path",
            conversation=[
                ConversationTurn(role="caller", text="I'd like to schedule an appointment with Dr. Patel"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        intent="schedule_appointment",
                        must_ask=["preferred_date"],
                        max_latency_ms=800,
                    ),
                ),
                ConversationTurn(role="caller", text="Next Tuesday afternoon please"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        must_include=["tuesday"],
                        must_extract={"date": "tuesday", "time_preference": "afternoon"},
                    ),
                ),
            ],
            tool_mocks=[
                ToolMock(
                    name="check_availability",
                    when_called_with={"doctor": "Dr. Patel"},
                    returns={"slots": ["2:00 PM", "3:30 PM"]},
                ),
            ],
            success_criteria=[
                SuccessCriterion(type="task_completion", description="Appointment offered"),
                SuccessCriterion(type="latency", p95_max_ms=1500),
            ],
        ),
        Scenario(
            id="quick-order-003",
            description="Order status inquiry",
            conversation=[
                ConversationTurn(role="caller", text="I want to check on my order status"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        intent="order_status",
                        must_ask=["order_number"],
                    ),
                ),
                ConversationTurn(role="caller", text="My order number is 1 2 3 4 5"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        must_extract={"order_number": "12345"},
                    ),
                ),
            ],
            tool_mocks=[
                ToolMock(
                    name="lookup_order",
                    when_called_with={"order_id": "12345"},
                    returns={"status": "shipped", "eta": "Thursday"},
                ),
            ],
            success_criteria=[
                SuccessCriterion(type="task_completion", description="Order status provided"),
            ],
        ),
        Scenario(
            id="quick-transfer-004",
            description="Request to speak with a human",
            conversation=[
                ConversationTurn(role="caller", text="I'd like to speak with a real person please"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        intent="transfer_to_human",
                        must_include=["transfer", "connect"],
                        max_latency_ms=600,
                    ),
                ),
            ],
            success_criteria=[
                SuccessCriterion(type="task_completion", description="Transfer initiated or offered"),
            ],
        ),
        Scenario(
            id="quick-noisy-005",
            description="Conversation in cafe noise",
            persona=Persona(background_noise="cafe", noise_level_db=15.0),
            conversation=[
                ConversationTurn(role="caller", text="Hi, I need to cancel my subscription"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        intent="cancel_subscription",
                        max_latency_ms=1000,
                    ),
                ),
            ],
            success_criteria=[
                SuccessCriterion(type="task_completion"),
                SuccessCriterion(type="latency", p95_max_ms=2000),
            ],
        ),
        Scenario(
            id="quick-clarification-006",
            description="Agent asks for clarification",
            conversation=[
                ConversationTurn(role="caller", text="Mmm yeah the thing with the stuff"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        must_ask=["clarify", "help", "specific"],
                    ),
                ),
            ],
            success_criteria=[
                SuccessCriterion(type="task_completion", description="Agent asks for clarification"),
            ],
        ),
        Scenario(
            id="quick-multiintent-007",
            description="Multiple intents in one utterance",
            conversation=[
                ConversationTurn(
                    role="caller",
                    text="I need to change my address and also update my payment method",
                ),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        intent="multi_intent",
                        must_include=["address"],
                    ),
                ),
            ],
            success_criteria=[
                SuccessCriterion(type="task_completion", description="Both intents acknowledged"),
            ],
        ),
        Scenario(
            id="quick-fast-008",
            description="Fast speech speed test",
            persona=Persona(speaking_speed=1.5),
            conversation=[
                ConversationTurn(
                    role="caller",
                    text="I need to reschedule my appointment from Wednesday to Friday at ten AM",
                ),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        must_extract={"day": "friday", "time": "10"},
                    ),
                ),
            ],
            success_criteria=[
                SuccessCriterion(type="task_completion"),
            ],
        ),
        Scenario(
            id="quick-farewell-009",
            description="Polite conversation closing",
            conversation=[
                ConversationTurn(role="caller", text="That's all I needed, thank you very much"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        intent="farewell",
                        must_include=["thank"],
                    ),
                ),
            ],
            success_criteria=[
                SuccessCriterion(type="task_completion", description="Polite farewell"),
            ],
        ),
        Scenario(
            id="quick-error-010",
            description="Agent handles system error gracefully",
            conversation=[
                ConversationTurn(role="caller", text="Can you check my account balance?"),
                ConversationTurn(
                    role="agent",
                    expect=TurnExpectation(
                        intent="account_balance",
                    ),
                ),
            ],
            tool_mocks=[
                ToolMock(
                    name="get_balance",
                    when_called_with={},
                    returns={"error": "Service temporarily unavailable"},
                ),
            ],
            success_criteria=[
                SuccessCriterion(
                    type="task_completion",
                    description="Agent handles error gracefully, doesn't crash",
                ),
            ],
        ),
    ]
    return scenarios


def _generate_extended_scenarios() -> list[Scenario]:
    """Generate 40 additional scenarios for the standard suite."""
    from decibench.models import ConversationTurn, Persona, SuccessCriterion, TurnExpectation

    extended: list[Scenario] = []
    base_scenarios = [
        ("std-billing-", "Billing inquiry", "I have a question about my last bill"),
        ("std-password-", "Password reset", "I need to reset my password"),
        ("std-return-", "Product return", "I'd like to return an item I purchased"),
        ("std-complaint-", "Service complaint", "I want to file a complaint about my service"),
        ("std-upgrade-", "Plan upgrade", "I'm interested in upgrading my plan"),
        ("std-tech-", "Technical support", "My device isn't working properly"),
        ("std-shipping-", "Shipping inquiry", "Where is my package?"),
        ("std-refund-", "Refund request", "I'd like a refund please"),
    ]

    noises = ["clean", "cafe", "street", "car", "office"]
    idx = 11

    for base_id, desc, text in base_scenarios:
        for noise in noises:
            extended.append(Scenario(
                id=f"{base_id}{idx:03d}",
                description=f"{desc} ({noise} noise)",
                persona=Persona(
                    background_noise=noise,
                    noise_level_db=15.0 if noise != "clean" else 0.0,
                ),
                conversation=[
                    ConversationTurn(role="caller", text=text),
                    ConversationTurn(
                        role="agent",
                        expect=TurnExpectation(max_latency_ms=1000),
                    ),
                ],
                success_criteria=[
                    SuccessCriterion(type="task_completion"),
                    SuccessCriterion(type="latency", p95_max_ms=1500),
                ],
            ))
            idx += 1

    return extended[:40]
