"""
Unit tests for the dq.run runner module.
Tests exit code behavior for ERROR vs WARNING failures.
"""

import pytest
from fixtures.generator import FixtureGenerator
from dq.backends.fake import FakeBackend
from dq.engine import QualityEngine
from dq.discovery import ConfigDiscovery
from dq.schema import TableConfig, Check, CheckType, Severity


def test_runner_exits_non_zero_on_error_failures():
    """Test runner exits with code 1 when ERROR checks fail"""
    from dq.__main__ import main
    
    # The runner loads real configs which have 3 ERROR bugs planted
    # So it should exit with code 1
    with pytest.raises(SystemExit) as exc_info:
        main()
    
    assert exc_info.value.code == 1, "Should exit with code 1 on ERROR failures"


def test_runner_exits_zero_on_warning_only_failures():
    """Test runner exits with code 0 when only WARNING checks fail"""
    # Create a scenario where only WARNING checks fail
    generator = FixtureGenerator()
    fixtures = generator.generate()
    backend = FakeBackend(fixtures)
    
    discovery = ConfigDiscovery()
    table_configs = discovery.discover()
    
    # Disable all ERROR checks (the 3 planted bugs)
    for tc in table_configs:
        for check in tc.checks:
            if check.config.get("severity") == "ERROR":
                check.enabled = False
    
    # Run engine
    engine = QualityEngine(backend)
    result = engine.run_checks(table_configs)
    
    # Should have no error failures
    assert result.error_failures == 0, "Should have no ERROR failures"
    assert result.should_halt == False, "Should not halt on WARNING only"
