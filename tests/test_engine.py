"""
Unit tests for the data quality engine using fake backend.
Tests run without any database connection.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fixtures.generator import FixtureGenerator
from dq.backends.fake import FakeBackend
from dq.engine import QualityEngine
from dq.discovery import ConfigDiscovery
from dq.schema import Severity


class TestQualityEngine:
    """Test the quality engine with fake backend"""

    @pytest.fixture
    def fixtures(self):
        """Generate fixture data for testing"""
        generator = FixtureGenerator()
        return generator.generate()

    @pytest.fixture
    def backend(self, fixtures):
        """Create fake backend with fixtures"""
        return FakeBackend(fixtures)

    @pytest.fixture
    def engine(self, backend):
        """Create quality engine with fake backend"""
        return QualityEngine(backend)

    @pytest.fixture
    def table_configs(self):
        """Load table configurations from YAML"""
        discovery = ConfigDiscovery()
        return discovery.discover()

    def test_backend_row_count(self, backend):
        """Test backend returns correct row counts"""
        assert backend.get_row_count("organisations") == 3
        assert backend.get_row_count("advisors") == 6
        assert backend.get_row_count("accounts") == 9

    def test_backend_count_null_values(self, backend):
        """Test backend counts NULL values correctly"""
        # Bug #1: One contact has NULL organisation_id
        null_count = backend.count_null_values("contacts", "organisation_id")
        assert null_count == 1, "Should detect 1 NULL organisation_id in contacts"

    def test_backend_count_duplicate_keys(self, backend):
        """Test backend counts duplicate keys correctly"""
        # Bug #2: Duplicate account_number within org_001
        dup_count = backend.count_duplicate_keys(
            "accounts",
            ["account_number"],
            group_by=["organisation_id"]
        )
        assert dup_count == 1, "Should detect 1 duplicate account_number"

    def test_backend_count_cross_tenant_violations(self, backend):
        """Test backend counts cross-tenant violations correctly"""
        # Bug #3: Holding in org_001 references portfolio from org_002
        violations = backend.count_cross_tenant_violations(
            "holdings",
            "portfolio_id",
            "portfolios",
            "id",
            "organisation_id"
        )
        assert violations == 1, "Should detect 1 cross-tenant violation"

    def test_backend_count_range_violations(self, backend):
        """Test backend counts range violations correctly"""
        # All transaction amounts should be within range
        violations = backend.count_range_violations(
            "transactions",
            "amount",
            min_value=0,
            max_value=1000000
        )
        assert violations == 0, "All transaction amounts should be within range"

    def test_engine_runs_all_checks(self, engine, table_configs):
        """Test engine runs all checks from table configs"""
        result = engine.run_checks(table_configs)
        assert result.total_checks > 0, "Should run at least one check"
        assert len(result.check_results) == result.total_checks

    def test_engine_detects_null_bug(self, engine, table_configs):
        """Test engine detects Bug #1: NULL organisation_id"""
        result = engine.run_checks(table_configs)
        
        # Find the contact null check result
        contact_null_result = None
        for check_result in result.check_results:
            if check_result.table_name == "contacts" and "null" in check_result.check_name.lower():
                contact_null_result = check_result
                break
        
        assert contact_null_result is not None, "Should have contact null check"
        assert not contact_null_result.passed, "Contact null check should fail"
        assert contact_null_result.violation_count == 1, "Should detect 1 violation"

    def test_engine_detects_duplicate_key_bug(self, engine, table_configs):
        """Test engine detects Bug #2: Duplicate business key"""
        result = engine.run_checks(table_configs)
        
        # Find the account unique key check result
        account_unique_result = None
        for check_result in result.check_results:
            if check_result.table_name == "accounts" and "unique" in check_result.check_name.lower():
                account_unique_result = check_result
                break
        
        assert account_unique_result is not None, "Should have account unique key check"
        assert not account_unique_result.passed, "Account unique key check should fail"
        assert account_unique_result.violation_count == 1, "Should detect 1 violation"

    def test_engine_detects_cross_tenant_bug(self, engine, table_configs):
        """Test engine detects Bug #3: Cross-tenant leak"""
        result = engine.run_checks(table_configs)
        
        # Find the holdings cross-tenant check result
        holdings_cross_tenant_result = None
        for check_result in result.check_results:
            if check_result.table_name == "holdings" and "cross" in check_result.check_name.lower():
                holdings_cross_tenant_result = check_result
                break
        
        assert holdings_cross_tenant_result is not None, "Should have holdings cross-tenant check"
        assert not holdings_cross_tenant_result.passed, "Holdings cross-tenant check should fail"
        assert holdings_cross_tenant_result.violation_count == 1, "Should detect 1 violation"

    def test_engine_error_halts_execution(self, engine, table_configs):
        """Test engine sets should_halt when ERROR checks fail"""
        result = engine.run_checks(table_configs)
        
        # We have 3 ERROR-level bugs planted, so should_halt should be True
        assert result.should_halt, "Engine should halt when ERROR checks fail"
        assert result.error_failures > 0, "Should have error failures"

    def test_engine_severity_handling(self, engine, table_configs):
        """Test engine correctly handles ERROR vs WARNING severity"""
        result = engine.run_checks(table_configs)
        
        # Count ERROR and WARNING failures
        error_results = [r for r in result.check_results if not r.passed and r.severity == Severity.ERROR]
        warning_results = [r for r in result.check_results if not r.passed and r.severity == Severity.WARNING]
        
        # We planted 3 ERROR bugs
        assert len(error_results) >= 3, "Should detect at least 3 ERROR-level failures"

    def test_counts_only_rule(self, backend):
        """Test backend only returns counts, never raw rows"""
        # All backend methods return integers (counts)
        assert isinstance(backend.get_row_count("organisations"), int)
        assert isinstance(backend.count_null_values("contacts", "organisation_id"), int)
        assert isinstance(backend.count_duplicate_keys("accounts", ["account_number"]), int)
        assert isinstance(backend.count_cross_tenant_violations(
            "holdings", "portfolio_id", "portfolios", "id", "organisation_id"
        ), int)
        assert isinstance(backend.count_range_violations("transactions", "amount", 0, 1000000), int)

    def test_engine_result_aggregation(self, engine, table_configs):
        """Test engine correctly aggregates results"""
        result = engine.run_checks(table_configs)
        
        # Verify aggregation math
        assert result.passed_checks + result.failed_checks == result.total_checks
        assert result.warning_failures + result.error_failures == result.failed_checks

    def test_disabled_checks_not_executed(self, engine, table_configs):
        """Test disabled checks are not executed"""
        # Disable one check
        table_configs[0].checks[0].enabled = False
        
        result = engine.run_checks(table_configs)
        
        # Total checks should be less than total available
        assert result.total_checks < sum(len(tc.checks) for tc in table_configs)
