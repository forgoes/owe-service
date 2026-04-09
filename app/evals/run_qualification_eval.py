from __future__ import annotations

from app.evals.qualification_cases import CASES
from app.schemas.chat import ChatRequest
from app.services.graph import run_lead_agent


def run() -> int:
    failures: list[str] = []

    for index, case in enumerate(CASES, start=1):
        outcome = run_lead_agent(
            ChatRequest(
                session_id=f"eval-{index}",
                message=case.message,
            ),
            previous_state=None,
        )

        actual_tier = outcome.state.qualification.tier
        actual_missing_fields = tuple(outcome.state.missing_fields)

        if actual_tier != case.expected_tier:
            failures.append(
                f"[{case.name}] expected tier={case.expected_tier.value}, got {actual_tier.value}"
            )

        if case.expected_missing_fields and actual_missing_fields != case.expected_missing_fields:
            failures.append(
                f"[{case.name}] expected missing_fields={case.expected_missing_fields}, "
                f"got {actual_missing_fields}"
            )

    if failures:
        print("Qualification evaluation failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print(f"Qualification evaluation passed: {len(CASES)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
