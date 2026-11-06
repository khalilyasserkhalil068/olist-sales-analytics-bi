"""Separate audit tests: do not alter the original cleaning regression suite."""
import os
from pathlib import Path

import pytest

from phase_2_audit import GROUPS, IndependentAudit


@pytest.fixture(scope="session")
def independent_audit():
    audit = IndependentAudit(Path(__file__).resolve().parents[1]).run()
    yield audit
    if os.environ.get("PHASE2_AUDIT_WRITE") == "1":
        audit.write_reports(pytest_scenarios=len(GROUPS))


@pytest.mark.parametrize("category", GROUPS)
def test_independent_phase_2_category(independent_audit, category):
    checks = [row for row in independent_audit.results if row["category"] == category]
    assert checks, f"NOT VERIFIED: no checks executed for {category}"
    failures = [row for row in checks if row["status"] == "FAIL"]
    assert not failures, "\n".join(f"{row['test_name']}: {row['actual_behavior']} Evidence={row['evidence']}" for row in failures)
    if all(row["status"] == "NOT VERIFIED" for row in checks):
        pytest.skip("NOT VERIFIED: " + "; ".join(row["test_name"] for row in checks))
