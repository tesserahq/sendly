"""Transaction-ownership guards (tessera_sdk.testing.transaction_guards).

Regenerate the baseline after removing violations with
``UPDATE_TRANSACTION_BASELINE=1 ENV=test poetry run pytest tests/architecture``.
"""

from pathlib import Path

import pytest
from tessera_sdk.testing.transaction_guards import (
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
)


@pytest.mark.parametrize("rule", RULE_NAMES)
def test_transaction_rule_matches_baseline(rule):
    assert_matches_baseline(CONFIG, rule)
