"""
Contract tests for ClickHouse backend.
These tests verify that ClickHouse backend implements the same semantics as the fake backend.
Tests are skipped automatically when ClickHouse is not running.
"""

import pytest
import clickhouse_connect
from clickhouse_connect.driver.exceptions import Error as ClickHouseError

from dq.backends.clickhouse import ClickHouseBackend, BackendError
from dq.autogen import generate_checks
from dq.discovery import ConfigDiscovery
from dq.engine import QualityEngine
from dq.schema import Severity


def is_clickhouse_running():
    """Check if ClickHouse is available"""
    try:
        client = clickhouse_connect.get_client(
            host='localhost',
            port=8123,
            username='default',
            password='',
            database='data_quality'
        )
        client.close()
        return True
    except ClickHouseError:
        return False


# Skip all tests if ClickHouse is not running
pytestmark = pytest.mark.skipif(
    not is_clickhouse_running(),
    reason="ClickHouse is not running. Start with: docker-compose up -d"
)


class TestClickHouseBackendContract:
    """Contract tests for ClickHouse backend"""

    @pytest.fixture
    def backend(self):
        """Create ClickHouse backend"""
        return ClickHouseBackend(
            host='localhost',
            port=8123,
            username='default',
            password='',
            database='data_quality'
        )

    def test_get_row_count(self, backend):
        """Test get_row_count returns integer"""
        count = backend.get_row_count("organisations")
        assert isinstance(count, int)
        assert count >= 0

    def test_count_null_values(self, backend):
        """Test count_null_values returns integer count of NULLs"""
        # contacts has 1 NULL organisation_id (planted bug)
        count = backend.count_null_values("contacts", "organisation_id")
        assert isinstance(count, int)
        assert count == 1, "Should detect exactly 1 NULL organisation_id in contacts"

    def test_count_duplicate_keys_global(self, backend):
        """Test count_duplicate_keys counts duplicates globally"""
        # accounts has 1 duplicate account_number (planted bug)
        count = backend.count_duplicate_keys("accounts", ["account_number"])
        assert isinstance(count, int)
        assert count == 1, "Should detect exactly 1 duplicate account_number"

    def test_count_duplicate_keys_grouped(self, backend):
        """Test count_duplicate_keys counts duplicates within groups"""
        # accounts has 1 duplicate account_number within org_001
        count = backend.count_duplicate_keys("accounts", ["account_number"], group_by=["organisation_id"])
        assert isinstance(count, int)
        assert count == 1, "Should detect exactly 1 duplicate within group"

    def test_count_cross_tenant_violations(self, backend):
        """Test count_cross_tenant_violations detects cross-tenant refs"""
        # holdings has 1 cross-tenant violation (planted bug)
        count = backend.count_cross_tenant_violations(
            "holdings", "portfolio_id", "portfolios", "id", "organisation_id"
        )
        assert isinstance(count, int)
        assert count == 1, "Should detect exactly 1 cross-tenant violation"

    def test_count_range_violations(self, backend):
        """Test count_range_violations counts values outside range"""
        # Test with a range that excludes some values
        count = backend.count_range_violations("accounts", "balance", min_value=1500, max_value=1800)
        assert isinstance(count, int)
        assert count >= 0

    def test_unknown_table_error(self, backend):
        """Test that unknown table raises BackendError"""
        with pytest.raises(BackendError) as exc_info:
            backend.get_row_count("nonexistent_table")
        assert "Unknown table" in str(exc_info.value)

    def test_unknown_column_error(self, backend):
        """Test that unknown column raises BackendError"""
        with pytest.raises(BackendError) as exc_info:
            backend.count_null_values("organisations", "nonexistent_column")
        assert "Unknown column" in str(exc_info.value)

    def test_counts_only_no_data_leak(self, backend):
        """Test that backend only returns counts, never row data"""
        # All methods return integers
        assert isinstance(backend.get_row_count("organisations"), int)
        assert isinstance(backend.count_null_values("contacts", "organisation_id"), int)
        assert isinstance(backend.count_duplicate_keys("accounts", ["account_number"]), int)
        assert isinstance(backend.count_cross_tenant_violations(
            "holdings", "portfolio_id", "portfolios", "id", "organisation_id"
        ), int)
        assert isinstance(backend.count_range_violations("accounts", "balance", 0, 1000000), int)

    def test_get_table_columns(self, backend):
        """Test that get_table_columns returns column names"""
        columns = backend.get_table_columns("accounts")
        assert isinstance(columns, list)
        assert len(columns) > 0
        assert "id" in columns
        assert "organisation_id" in columns
        assert "account_number" in columns

    def test_auto_generation_with_clickhouse(self, backend):
        """Test that auto-generated checks run on ClickHouse and find 0 violations apart from planted bugs"""
        # Load real configs
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        # Apply auto-generation
        table_configs = generate_checks(table_configs, backend)
        
        # Run engine
        engine = QualityEngine(backend)
        result = engine.run_checks(table_configs)
        
        # Should have exactly 3 ERROR failures (the planted bugs)
        assert result.error_failures == 3
        assert result.warning_failures == 0
        
        # Auto-generated checks should have 0 violations
        auto_check_results = [r for r in result.check_results if r.check_name.startswith("auto_")]
        for auto_result in auto_check_results:
            assert auto_result.violation_count == 0, f"Auto-generated check {auto_result.check_name} should have 0 violations"
