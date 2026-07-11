import json
from datetime import date

from agent_commerce.orchestration import brain
from agent_commerce.orchestration.brain import PurchaseIntentOutput


def test_agent_exchange_is_appended_as_json_line(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "agent_log"
    monkeypatch.setattr(brain, "AGENT_LOG_PATH", log_path)
    response = PurchaseIntentOutput(
        product_query="monitor for Mac",
        category="monitor",
        quantity=1,
        max_budget_minor=120_000,
        currency="PLN",
        required_attributes=(),
        latest_delivery_date=date(2026, 7, 12),
        minimum_return_window_days=30,
        purchase_if_confident=True,
        missing_required_fields=(),
        clarification_questions=(),
    )

    brain._log_agent_exchange("Purchase intent interpreter", "Kup monitor", response)

    entry = json.loads(log_path.read_text(encoding="utf-8"))
    assert entry["agent"] == "Purchase intent interpreter"
    assert entry["request"] == "Kup monitor"
    assert entry["response"]["max_budget_minor"] == 120_000
    assert entry["timestamp"].endswith("+00:00")
