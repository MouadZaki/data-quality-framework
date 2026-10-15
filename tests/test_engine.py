"""
Unit tests for the data quality engine using fake backend.
Tests run without any database connection.
"""

import pytest
from fixtures.generator import FixtureGenerator
from dq.backends.fake import FakeBackend, BackendError
from dq.engine import QualityEngine
from dq.discovery import ConfigDiscovery
from dq.schema import Severity


class TestQualityEngine:
    """Test the quality engine with fake backend"""

    @pytest.fixture
    def fixtures(self):
        """Generate fixture data for testing"""
        generator = FixtureGenerator(verbose=False)
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

    def test_clean_data_passes_all_checks(self):
        """Test that clean data (no planted bugs) passes all checks with no failures"""
        # Generate clean fixtures without planted bugs
        generator = FixtureGenerator(verbose=False, plant_bugs=False)
        clean_fixtures = generator.generate()
        
        # Create backend with clean data
        backend = FakeBackend(clean_fixtures)
        
        # Load configs and run engine
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        engine = QualityEngine(backend)
        result = engine.run_checks(table_configs)
        
        # All checks should pass with no failures
        assert result.error_failures == 0
        assert result.warning_failures == 0
        assert result.total_checks > 0  # Should have checks running

    def test_backend_row_count(self, backend, fixtures):
        """Test backend returns correct row counts"""
        assert backend.get_row_count("organisations") == len(fixtures.organisations)
        assert backend.get_row_count("advisors") == len(fixtures.advisors)
        assert backend.get_row_count("accounts") == len(fixtures.accounts)

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
        
        # Find the contact null check result by exact name
        contact_null_result = None
        for check_result in result.check_results:
            if check_result.table_name == "contacts" and check_result.check_name == "contact_org_id_not_null":
                contact_null_result = check_result
                break
        
        assert contact_null_result is not None, "Should have contact_org_id_not_null check"
        assert not contact_null_result.passed, "Contact null check should fail"
        assert contact_null_result.violation_count == 1, "Should detect 1 violation"

    def test_engine_detects_duplicate_key_bug(self, engine, table_configs):
        """Test engine detects Bug #2: Duplicate business key"""
        result = engine.run_checks(table_configs)
        
        # Find the account_number unique key check result by exact name
        account_unique_result = None
        for check_result in result.check_results:
            if check_result.table_name == "accounts" and check_result.check_name == "account_number_unique_per_org":
                account_unique_result = check_result
                break
        
        assert account_unique_result is not None, "Should have account_number_unique_per_org check"
        assert not account_unique_result.passed, "Account unique key check should fail"
        assert account_unique_result.violation_count == 1, "Should detect 1 violation"

    def test_engine_detects_cross_tenant_bug(self, engine, table_configs):
        """Test engine detects Bug #3: Cross-tenant leak"""
        result = engine.run_checks(table_configs)
        
        # Find the holdings cross-tenant check result by exact name
        holdings_cross_tenant_result = None
        for check_result in result.check_results:
            if check_result.table_name == "holdings" and check_result.check_name == "holding_portfolio_cross_tenant":
                holdings_cross_tenant_result = check_result
                break
        
        assert holdings_cross_tenant_result is not None, "Should have holding_portfolio_cross_tenant check"
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
        
        # We planted exactly 3 ERROR bugs
        assert len(error_results) == 3, "Should detect exactly 3 ERROR-level failures"

    def test_exactly_three_planted_bugs_reported(self, engine, table_configs):
        """Test exactly the 3 planted bugs are reported, all others pass"""
        result = engine.run_checks(table_configs)
        
        # The 3 planted bugs:
        planted_bugs = [
            ("contacts", "contact_org_id_not_null"),
            ("accounts", "account_number_unique_per_org"),
            ("holdings", "holding_portfolio_cross_tenant")
        ]
        
        # Check that these 3 fail
        for table_name, check_name in planted_bugs:
            result_for_bug = None
            for check_result in result.check_results:
                if check_result.table_name == table_name and check_result.check_name == check_name:
                    result_for_bug = check_result
                    break
            assert result_for_bug is not None, f"Should have check {table_name}.{check_name}"
            assert not result_for_bug.passed, f"{table_name}.{check_name} should fail"
            assert result_for_bug.violation_count == 1, f"{table_name}.{check_name} should have 1 violation"
        
        # Check that all other checks pass
        failed_checks = [(r.table_name, r.check_name) for r in result.check_results if not r.passed]
        assert set(failed_checks) == set(planted_bugs), f"Only planted bugs should fail, but got: {failed_checks}"

    def test_warning_failure_does_not_halt(self, engine, table_configs):
        """Test a failing WARNING check does not halt execution"""
        from dq.schema import TableConfig, Check, CheckType
        from fixtures.generator import FixtureGenerator
        
        # Create a custom table config with a WARNING check that will fail
        custom_config = TableConfig(
            table_name="accounts",  # Use existing table
            description="Test table",
            tenant_column="organisation_id",
            is_shared_reference=False,
            checks=[
                Check(
                    name="test_warning_check",
                    type=CheckType.NULL_CHECK,
                    config={"column": "organisation_id", "severity": "WARNING"},
                    severity=Severity.WARNING,
                    description="Test WARNING check",
                    enabled=True
                )
            ]
        )
        
        # Create a backend that will return a violation for this check
        class TestBackend(FakeBackend):
            def count_null_values(self, table_name: str, column: str) -> int:
                if table_name == "accounts" and column == "organisation_id":
                    return 1  # Simulate a violation
                return super().count_null_values(table_name, column)
        
        # Get fresh fixtures
        generator = FixtureGenerator(verbose=False)
        fixtures = generator.generate()
        test_backend = TestBackend(fixtures)
        test_engine = QualityEngine(test_backend)
        
        result = test_engine.run_checks([custom_config])
        
        # Should have 1 WARNING failure
        assert result.warning_failures == 1, "Should have 1 WARNING failure"
        assert result.error_failures == 0, "Should have 0 ERROR failures"
        assert result.should_halt == False, "Should not halt on WARNING failure"

    def test_disabled_check_not_executed(self, engine, table_configs):
        """Test disabled checks are not executed"""
        # Count total enabled checks before disabling
        total_enabled_before = sum(1 for tc in table_configs for check in tc.checks if check.enabled)
        
        # Disable one check
        table_configs[0].checks[0].enabled = False
        
        result = engine.run_checks(table_configs)
        
        # Total checks should be one less
        assert result.total_checks == total_enabled_before - 1, "Disabled check should not be executed"

    def test_backend_unknown_table_error(self, backend):
        """Test backend raises clear error for unknown table"""
        with pytest.raises(BackendError) as exc_info:
            backend.get_row_count("unknown_table")
        assert "Unknown table" in str(exc_info.value)
        assert "unknown_table" in str(exc_info.value)

    def test_backend_unknown_referenced_table_error(self, backend):
        """Test backend raises clear error for unknown referenced table"""
        with pytest.raises(BackendError) as exc_info:
            backend.count_cross_tenant_violations(
                "holdings", "portfolio_id", "unknown_table", "id", "organisation_id"
            )
        assert "Unknown referenced table" in str(exc_info.value)

    def test_no_data_leak_in_error_messages(self, engine, table_configs):
        """Test error messages contain only exception type, not data"""
        # Create a backend that raises an exception with fake customer data
        class LeakyBackend(FakeBackend):
            def count_null_values(self, table_name: str, column: str) -> int:
                raise ValueError("Customer SSN: 123-45-6789 exposed in error")
        
        # Pass fixtures object instead of data dict
        generator = FixtureGenerator()
        fixtures = generator.generate()
        leaky_backend = LeakyBackend(fixtures)
        leaky_engine = QualityEngine(leaky_backend)
        
        result = leaky_engine.run_checks(table_configs)
        
        # Find the failed check result
        failed_result = None
        for check_result in result.check_results:
            if not check_result.passed and "ValueError" in check_result.message:
                failed_result = check_result
                break
        
        assert failed_result is not None, "Should have a failed check with ValueError"
        # Should only contain "ValueError", not the fake SSN
        assert "ValueError" in failed_result.message
        assert "123-45-6789" not in failed_result.message, "Error message should not contain customer data"
        assert "SSN" not in failed_result.message, "Error message should not contain customer data"

    def test_counts_only_no_row_data_in_results(self, engine, table_configs):
        """Test CheckResult fields contain no row data (IDs, values)"""
        result = engine.run_checks(table_configs)
        
        # Get fixture data to check against
        generator = FixtureGenerator()
        fixtures = generator.generate()
        
        # Collect all potential data values from fixtures
        fixture_values = set()
        for org in fixtures.organisations:
            fixture_values.add(org.id)
            fixture_values.add(org.name)
        
        # Check that no CheckResult message contains fixture data
        for check_result in result.check_results:
            for value in fixture_values:
                assert value not in check_result.message, f"CheckResult message should not contain row data: {value}"
        
        # Check that violation_count is always an integer
        for check_result in result.check_results:
            assert isinstance(check_result.violation_count, int), "violation_count must be integer"

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
        assert result.total_checks == sum(1 for tc in table_configs for check in tc.checks if check.enabled)


class TestBackendContractTests:
    """Contract tests with small hand-written datasets for backend methods"""

    @pytest.fixture
    def simple_backend(self):
        """Create a backend with simple hand-written data"""
        from fixtures.generator import Fixtures, Organisation, Account, Portfolio, Holding
        from dq.backends.fake import FakeBackend
        from datetime import datetime
        
        # Create simple fixtures with known data
        fixtures = Fixtures()
        
        # Add simple test data using actual dataclasses
        fixtures.organisations = [
            Organisation(id='org1', name='Org1', created_at=datetime.now()),
            Organisation(id='org2', name='Org2', created_at=datetime.now()),
        ]
        fixtures.accounts = [
            Account(id='acc1', organisation_id='org1', advisor_id='adv1', account_number='001', account_type='Brokerage', balance=1000),
            Account(id='acc2', organisation_id='org1', advisor_id='adv1', account_number='001', account_type='IRA', balance=2000),  # Duplicate account_number
            Account(id='acc3', organisation_id='org1', advisor_id='adv1', account_number='002', account_type='IRA', balance=None),  # NULL balance
        ]
        fixtures.portfolios = [
            Portfolio(id='prt1', organisation_id='org1', account_id='acc1', name='P1'),
            Portfolio(id='prt2', organisation_id='org2', account_id='acc2', name='P2'),
        ]
        fixtures.holdings = [
            Holding(id='hld1', organisation_id='org1', portfolio_id='prt1', security_id='sec1', quantity=10, avg_cost=100),
            Holding(id='hld2', organisation_id='org1', portfolio_id='prt2', security_id='sec2', quantity=20, avg_cost=200),  # Cross-tenant: org1 holding references org2 portfolio
        ]
        
        return FakeBackend(fixtures)

    def test_contract_count_null_values(self, simple_backend):
        """Contract test: count_null_values returns count of NULL values"""
        # accounts has 1 NULL balance
        count = simple_backend.count_null_values("accounts", "balance")
        assert count == 1, "Should count exactly 1 NULL value"

    def test_contract_count_duplicate_keys_global(self, simple_backend):
        """Contract test: count_duplicate_keys counts duplicates globally"""
        # accounts has duplicate account_number '001' (2 occurrences = 1 duplicate)
        count = simple_backend.count_duplicate_keys("accounts", ["account_number"])
        assert count == 1, "Should count 1 duplicate (2 occurrences - 1)"

    def test_contract_count_duplicate_keys_grouped(self, simple_backend):
        """Contract test: count_duplicate_keys counts duplicates within groups"""
        # All accounts in same org, duplicate account_number should be counted
        count = simple_backend.count_duplicate_keys("accounts", ["account_number"], group_by=["organisation_id"])
        assert count == 1, "Should count 1 duplicate within group"

    def test_contract_count_cross_tenant_violations(self, simple_backend):
        """Contract test: count_cross_tenant_violations detects cross-tenant refs"""
        # holdings.hld2 is in org1 but references prt2 which is in org2
        count = simple_backend.count_cross_tenant_violations(
            "holdings", "portfolio_id", "portfolios", "id", "organisation_id"
        )
        assert count == 1, "Should detect 1 cross-tenant violation"

    def test_contract_count_range_violations(self, simple_backend):
        """Contract test: count_range_violations counts values outside range"""
        # Test with a range that excludes some values
        count = simple_backend.count_range_violations("accounts", "balance", min_value=1500, max_value=1800)
        # balance 1000 is below range, 2000 is above range, NULL is not counted
        assert count == 2, "Should count 2 values outside range (NULL not counted)"
