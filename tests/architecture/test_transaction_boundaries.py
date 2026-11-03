"""Transaction-ownership guards (tessera_sdk.testing.transaction_guards).

Regenerate the baseline after removing violations with
``UPDATE_TRANSACTION_BASELINE=1 ENV=test poetry run pytest tests/architecture``.
"""

from pathlib import Path

import pytest
from tessera_sdk.testing.transaction_guards import (
    EVENT_LOOP_RULE_NAMES,
    RULE_NAMES,
    TransactionGuardConfig,
    assert_matches_baseline,
)

CONFIG = TransactionGuardConfig(
    app_root=Path(__file__).parents[2] / "app",
    baseline_path=Path(__file__).with_name("transaction_baseline.json"),
    # The SDK auth/onboarding user service is built from db_manager.
    session_modules=("db.py", "services/sdk_user_service.py"),
    repository_base_modules=(),
    early_commit_allowlist={
        ("commands/send_email_command.py", "execute"): (
            "email_queued: the provider call must not run inside a transaction"
        ),
        ("tasks/send_broadcast_chunk_task.py", "_send_chunk"): (
            "provider_input_ready: release the connection before Postmark"
        ),
    },
    # async def routes that must await (Custos authorization, the request
    # body) and run their database work via run_in_threadpool (linden-api
    # SDD 0012 §4, option 4): (path relative to app/, function) -> reason.
    async_db_allowlist={
        ("routers/broadcast.py", "get_broadcast"): (
            "awaits the Custos check against the batch's project; queries run "
            "in the threadpool"
        ),
        ("routers/broadcast.py", "list_broadcast_recipients"): (
            "awaits the Custos check against the batch's project; queries run "
            "in the threadpool"
        ),
        ("routers/provider.py", "receive_delivery_events"): (
            "awaits the raw webhook body; the command runs in the threadpool"
        ),
    },
)


@pytest.mark.parametrize("rule", RULE_NAMES)
def test_transaction_rule_matches_baseline(rule):
    assert_matches_baseline(CONFIG, rule)


@pytest.mark.parametrize("rule", EVENT_LOOP_RULE_NAMES)
def test_event_loop_rule_matches_baseline(rule):
    """Synchronous database access in ``async def`` blocks the event loop
    (linden-api SDD 0012)."""
    assert_matches_baseline(CONFIG, rule)
