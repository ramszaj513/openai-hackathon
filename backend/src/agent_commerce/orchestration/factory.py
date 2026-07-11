"""Environment-driven production composition for the commerce agent."""

from __future__ import annotations

import os
from typing import cast

from openai.types.shared.reasoning_effort import ReasoningEffort

from agent_commerce.commerce.service import CommerceService
from agent_commerce.orchestration.activity import ActivityReporter, TransactionActivityLog
from agent_commerce.orchestration.brain import (
    DeterministicOfferPlanner,
    IntentInterpreter,
    OfferPlanner,
    OpenAIIntentInterpreter,
    OpenAIOfferPlanner,
)
from agent_commerce.orchestration.merchant_gateway import (
    DirectMerchantGateway,
    MCPMerchantGateway,
    MerchantGateway,
)
from agent_commerce.orchestration.models import NormalizedPurchaseIntent
from agent_commerce.orchestration.service import CommerceOrchestrator
from agent_commerce.payments import PaymentService
from agent_commerce.trust import TrustService

VALID_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


class ModelDisabledIntentInterpreter:
    """Keep non-agent APIs available when model execution is explicitly disabled."""

    async def normalize(
        self,
        raw_request: str,
        reporter: ActivityReporter | None = None,
    ) -> NormalizedPurchaseIntent:
        raise RuntimeError(
            "Intent interpretation requires the OpenAI model; set AGENT_USE_OPENAI=1 "
            "and configure OPENAI_API_KEY and OPENAI_MODEL"
        )


def create_default_orchestrator(
    commerce: CommerceService,
    trust: TrustService,
    payments: PaymentService,
) -> CommerceOrchestrator:
    mcp_url = os.getenv("MCP_BASE_URL", "http://127.0.0.1:8000/mcp")
    use_mcp = os.getenv("AGENT_USE_MCP", "1").lower() not in {"0", "false", "no"}
    use_openai = os.getenv("AGENT_USE_OPENAI", "1").lower() not in {
        "0",
        "false",
        "no",
    }
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    merchant: MerchantGateway = (
        MCPMerchantGateway(mcp_url) if use_mcp else DirectMerchantGateway(commerce)
    )
    interpreter: IntentInterpreter
    planner: OfferPlanner
    if use_openai:
        if not has_key:
            raise RuntimeError("OPENAI_API_KEY is required when AGENT_USE_OPENAI is enabled")
        model = os.getenv("OPENAI_MODEL")
        if not model:
            raise RuntimeError("OPENAI_MODEL is required when AGENT_USE_OPENAI is enabled")
        configured_effort = os.getenv("OPENAI_REASONING_EFFORT", "high").lower()
        if configured_effort not in VALID_REASONING_EFFORTS:
            allowed = ", ".join(sorted(VALID_REASONING_EFFORTS))
            raise RuntimeError(f"OPENAI_REASONING_EFFORT must be one of: {allowed}")
        reasoning_effort = cast(ReasoningEffort, configured_effort)
        interpreter = OpenAIIntentInterpreter(model, reasoning_effort)
        planner = OpenAIOfferPlanner(model, mcp_url, reasoning_effort)
    else:
        interpreter = ModelDisabledIntentInterpreter()
        planner = DeterministicOfferPlanner(merchant)
    return CommerceOrchestrator(
        merchant=merchant,
        trust=trust,
        payments=payments,
        intent_interpreter=interpreter,
        offer_planner=planner,
        activities=TransactionActivityLog(),
    )
