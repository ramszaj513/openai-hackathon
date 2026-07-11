from __future__ import annotations

import pytest
from agent_commerce.commerce.service import CommerceService
from agent_commerce.orchestration.brain import (
    OpenAIIntentInterpreter,
    OpenAIOfferPlanner,
    PurchaseIntentOutput,
)
from agent_commerce.orchestration.factory import create_default_orchestrator
from agent_commerce.payments.service import PaymentService
from agent_commerce.trust.service import TrustService
from agents import AgentOutputSchema


def test_model_facing_intent_schema_is_strict() -> None:
    schema = AgentOutputSchema(PurchaseIntentOutput)

    assert schema.is_strict_json_schema()


def test_factory_applies_configured_model_and_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
) -> None:
    monkeypatch.setenv("AGENT_USE_OPENAI", "1")
    monkeypatch.setenv("AGENT_USE_MCP", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-sol")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "high")

    orchestrator = create_default_orchestrator(service, trust, payments)

    interpreter = orchestrator.intent_interpreter
    planner = orchestrator.offer_planner
    assert isinstance(interpreter, OpenAIIntentInterpreter)
    assert isinstance(planner, OpenAIOfferPlanner)
    assert interpreter.agent.model == "gpt-5.6-sol"
    assert interpreter.agent.model_settings.reasoning is not None
    assert interpreter.agent.model_settings.reasoning.effort == "high"
    assert planner.model == "gpt-5.6-sol"
    assert planner.reasoning_effort == "high"


def test_factory_rejects_unknown_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
    service: CommerceService,
    trust: TrustService,
    payments: PaymentService,
) -> None:
    monkeypatch.setenv("AGENT_USE_OPENAI", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-sol")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "extreme")

    with pytest.raises(RuntimeError, match="OPENAI_REASONING_EFFORT must be one of"):
        create_default_orchestrator(service, trust, payments)
