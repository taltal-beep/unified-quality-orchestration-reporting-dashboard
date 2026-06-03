"""Formal exit-code contract lock for :class:`EngineExitCode` (0–4).

Documents the mapping in [[Troubleshooting and Error Codes]] and guards against
accidental regressions during engine refactors.
"""

from __future__ import annotations

import pytest

from testo_core.engine.exit_codes import EngineExitCode, classify_exit_code


# Process-level contract: int values must remain stable for CI consumers.
@pytest.mark.parametrize(
    ("member", "value"),
    [
        (EngineExitCode.SUCCESS, 0),
        (EngineExitCode.DOMAIN_FAILURE, 1),
        (EngineExitCode.INVALID_INPUT, 2),
        (EngineExitCode.INFRA_FAILURE, 3),
        (EngineExitCode.INTERNAL_ERROR, 4),
    ],
)
def test_engine_exit_code_int_values(member: EngineExitCode, value: int) -> None:
    assert int(member) == value


@pytest.mark.parametrize(
    ("returncodes", "infra_error", "internal_failure", "expected"),
    [
        pytest.param([0], None, False, EngineExitCode.SUCCESS, id="EC-00-success"),
        pytest.param([0, 1], None, False, EngineExitCode.DOMAIN_FAILURE, id="EC-01-domain"),
        pytest.param([127], None, False, EngineExitCode.INFRA_FAILURE, id="EC-03a-missing-binary"),
        pytest.param([124], None, False, EngineExitCode.INFRA_FAILURE, id="EC-03b-timeout"),
        pytest.param([], RuntimeError("db"), False, EngineExitCode.INFRA_FAILURE, id="EC-03f-infra-error"),
        pytest.param([], None, False, EngineExitCode.INTERNAL_ERROR, id="EC-04b-empty-returncodes"),
        pytest.param([4], None, True, EngineExitCode.INTERNAL_ERROR, id="EC-04a-internal-failure"),
        pytest.param([0, 4], None, True, EngineExitCode.INTERNAL_ERROR, id="EC-04a-internal-mixed"),
        pytest.param([4], None, False, EngineExitCode.DOMAIN_FAILURE, id="EC-07-raw-rc4-not-internal"),
        pytest.param([137], None, False, EngineExitCode.DOMAIN_FAILURE, id="EC-sigkill-domain"),
    ],
)
def test_classify_exit_code_contract_matrix(
    returncodes: list[int],
    infra_error: Exception | None,
    internal_failure: bool,
    expected: EngineExitCode,
) -> None:
    assert (
        classify_exit_code(
            returncodes,
            infra_error=infra_error,
            internal_failure=internal_failure,
        )
        == expected
    )
