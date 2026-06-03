"""Parametrized tests for :func:`testo_core.engine.exit_codes.classify_exit_code`."""

from __future__ import annotations

import pytest

from testo_core.engine.exit_codes import EngineExitCode, classify_exit_code


@pytest.mark.parametrize(
    ("returncodes", "infra_error", "internal_failure", "expected"),
    [
        ([0, 0], None, False, EngineExitCode.SUCCESS),
        ([0, 1], None, False, EngineExitCode.DOMAIN_FAILURE),
        ([127], None, False, EngineExitCode.INFRA_FAILURE),
        ([124], None, False, EngineExitCode.INFRA_FAILURE),
        ([], RuntimeError("boom"), False, EngineExitCode.INFRA_FAILURE),
        ([], None, False, EngineExitCode.INTERNAL_ERROR),
        ([137], None, False, EngineExitCode.DOMAIN_FAILURE),
        ([4], None, False, EngineExitCode.DOMAIN_FAILURE),
        ([4], None, True, EngineExitCode.INTERNAL_ERROR),
        ([0, 4], None, True, EngineExitCode.INTERNAL_ERROR),
    ],
)
def test_classify_exit_code_matrix(
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
