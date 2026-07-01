"""Contract test: both execution stacks share a single EngineExitCode (Sprint 3 — Task 4.5).

After consolidation, ``testo_core.services.headless_engine.EngineExitCode`` and
``testo_core.engine.exit_codes.EngineExitCode`` must be the same class (not just
equal values), and ``classify_exit_code`` must be the same function.
"""

from __future__ import annotations

import pytest

from testo_core.engine.exit_codes import EngineExitCode as CanonicalExitCode
from testo_core.engine.exit_codes import classify_exit_code as canonical_classify
from testo_core.services.headless_engine import EngineExitCode as LegacyExitCode
from testo_core.services.headless_engine import classify_exit_code as legacy_classify


class TestExitCodeIdentity:
    def test_exit_code_is_same_class(self) -> None:
        assert CanonicalExitCode is LegacyExitCode

    def test_classify_is_same_function(self) -> None:
        assert canonical_classify is legacy_classify

    def test_all_members_present(self) -> None:
        expected = {"SUCCESS", "DOMAIN_FAILURE", "INVALID_INPUT", "INFRA_FAILURE", "INTERNAL_ERROR"}
        assert set(CanonicalExitCode.__members__.keys()) == expected

    @pytest.mark.parametrize(
        "returncodes, infra_error, expected",
        [
            ([0], None, CanonicalExitCode.SUCCESS),
            ([0, 0, 0], None, CanonicalExitCode.SUCCESS),
            ([1], None, CanonicalExitCode.DOMAIN_FAILURE),
            ([0, 1], None, CanonicalExitCode.DOMAIN_FAILURE),
            ([124], None, CanonicalExitCode.INFRA_FAILURE),
            ([127], None, CanonicalExitCode.INFRA_FAILURE),
            ([0, 127], None, CanonicalExitCode.INFRA_FAILURE),
            ([], None, CanonicalExitCode.INTERNAL_ERROR),
            ([0], RuntimeError("boom"), CanonicalExitCode.INFRA_FAILURE),
        ],
        ids=[
            "all-pass",
            "multi-pass",
            "single-fail",
            "mixed-fail",
            "timeout-124",
            "not-found-127",
            "mixed-infra",
            "empty-returncodes",
            "infra-error-exception",
        ],
    )
    def test_classify_produces_expected_exit_code(
        self,
        returncodes: list[int],
        infra_error: Exception | None,
        expected: CanonicalExitCode,
    ) -> None:
        assert canonical_classify(returncodes, infra_error=infra_error) == expected

    def test_cli_commands_use_canonical_exit_codes(self) -> None:
        from testo_core.cli.commands import config as config_cmd
        from testo_core.cli.commands import plans as plans_cmd

        assert hasattr(config_cmd, "EngineExitCode")
        assert config_cmd.EngineExitCode is CanonicalExitCode
        assert hasattr(plans_cmd, "EngineExitCode")
        assert plans_cmd.EngineExitCode is CanonicalExitCode
