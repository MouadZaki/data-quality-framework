"""
Unit tests for config discovery module.
Tests cover loading real configs and error handling for bad configs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import tempfile
import yaml
from dq.discovery import ConfigDiscovery, DiscoveryError
from dq.schema import CheckType


class TestConfigDiscovery:
    """Test config discovery and loading"""

    def test_all_real_configs_load(self):
        """Test all 10 real config files load successfully"""
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        # Should load exactly 10 table configs
        assert len(table_configs) == 10, f"Expected 10 configs, found {len(table_configs)}"
        
        # Verify table names
        table_names = [tc.table_name for tc in table_configs]
        expected_tables = [
            "organisations", "advisors", "accounts", "contacts",
            "securities", "portfolios", "holdings", "transactions",
            "trades", "fee_schedules"
        ]
        for expected in expected_tables:
            assert expected in table_names, f"Missing config for table: {expected}"

    def test_empty_yaml_file(self):
        """Test empty YAML file raises clear error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "empty.yaml"
            config_file.write_text("")
            
            discovery = ConfigDiscovery(str(tmpdir))
            
            with pytest.raises(DiscoveryError) as exc_info:
                discovery.discover()
            
            assert "Empty YAML file" in str(exc_info.value)
            assert "empty.yaml" in str(exc_info.value)

    def test_duplicate_table_name(self):
        """Test duplicate table_name across configs raises clear error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config1 = Path(tmpdir) / "table1.yaml"
            config2 = Path(tmpdir) / "table2.yaml"
            
            config_data = {
                "table_name": "duplicate_table",
                "description": "Test table",
                "tenant_column": "organisation_id",
                "is_shared_reference": False,
                "checks": []
            }
            
            config1.write_text(yaml.dump(config_data))
            config2.write_text(yaml.dump(config_data))
            
            discovery = ConfigDiscovery(str(tmpdir))
            
            with pytest.raises(DiscoveryError) as exc_info:
                discovery.discover()
            
            assert "Duplicate table_name" in str(exc_info.value)
            assert "duplicate_table" in str(exc_info.value)

    def test_duplicate_check_name(self):
        """Test duplicate check name within a table raises clear error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.yaml"
            
            config_data = {
                "table_name": "test_table",
                "description": "Test table",
                "tenant_column": "organisation_id",
                "is_shared_reference": False,
                "checks": [
                    {
                        "name": "duplicate_check",
                        "type": "null_check",
                        "config": {"column": "test_col"},
                        "severity": "ERROR",
                        "description": "First check",
                        "enabled": True
                    },
                    {
                        "name": "duplicate_check",
                        "type": "null_check",
                        "config": {"column": "other_col"},
                        "severity": "ERROR",
                        "description": "Second check",
                        "enabled": True
                    }
                ]
            }
            
            config_file.write_text(yaml.dump(config_data))
            
            discovery = ConfigDiscovery(str(tmpdir))
            
            with pytest.raises(DiscoveryError) as exc_info:
                discovery.discover()
            
            assert "Duplicate check name" in str(exc_info.value)
            assert "duplicate_check" in str(exc_info.value)

    def test_invalid_check_type(self):
        """Test invalid check type raises clear error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.yaml"
            
            config_data = {
                "table_name": "test_table",
                "description": "Test table",
                "tenant_column": "organisation_id",
                "is_shared_reference": False,
                "checks": [
                    {
                        "name": "invalid_type_check",
                        "type": "not_a_real_check_type",
                        "config": {"column": "test_col"},
                        "severity": "ERROR",
                        "description": "Invalid type",
                        "enabled": True
                    }
                ]
            }
            
            config_file.write_text(yaml.dump(config_data))
            
            discovery = ConfigDiscovery(str(tmpdir))
            
            with pytest.raises(DiscoveryError) as exc_info:
                discovery.discover()
            
            # Pydantic validates check type before our custom validation
            assert "Invalid table configuration" in str(exc_info.value)
            assert "not_a_real_check_type" in str(exc_info.value)

    def test_missing_required_field(self):
        """Test missing required field raises clear error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.yaml"
            
            # Missing required 'table_name' field
            config_data = {
                "description": "Test table",
                "tenant_column": "organisation_id",
                "is_shared_reference": False,
                "checks": []
            }
            
            config_file.write_text(yaml.dump(config_data))
            
            discovery = ConfigDiscovery(str(tmpdir))
            
            with pytest.raises(DiscoveryError) as exc_info:
                discovery.discover()
            
            assert "Invalid table configuration" in str(exc_info.value)

    def test_planted_bug_coverage(self):
        """Test configs cover all 3 planted bugs"""
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        # Build lookup by table name
        configs_by_table = {tc.table_name: tc for tc in table_configs}
        
        # Bug #1: contacts should have null_check on organisation_id
        contacts_config = configs_by_table["contacts"]
        contacts_null_checks = [
            c for c in contacts_config.checks
            if c.type == "null_check" and c.config.get("column") == "organisation_id"
        ]
        assert len(contacts_null_checks) >= 1, "contacts should have null_check on organisation_id"
        
        # Bug #2: accounts should have unique_key on account_number grouped by organisation_id
        accounts_config = configs_by_table["accounts"]
        accounts_unique_checks = [
            c for c in accounts_config.checks
            if c.type == "unique_key" 
            and c.config.get("columns") == ["account_number"]
            and c.config.get("group_by") == ["organisation_id"]
        ]
        assert len(accounts_unique_checks) >= 1, "accounts should have unique_key on account_number grouped by organisation_id"
        
        # Bug #3: holdings should have cross_tenant_check on portfolio_id referencing portfolios.id
        holdings_config = configs_by_table["holdings"]
        holdings_cross_tenant_checks = [
            c for c in holdings_config.checks
            if c.type == "cross_tenant_check"
            and c.config.get("column") == "portfolio_id"
            and c.config.get("referenced_table") == "portfolios"
            and c.config.get("referenced_column") == "id"
        ]
        assert len(holdings_cross_tenant_checks) >= 1, "holdings should have cross_tenant_check on portfolio_id referencing portfolios.id"

    def test_configs_load_order_is_stable(self):
        """Test configs load in stable (sorted) order"""
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        # Load again
        discovery2 = ConfigDiscovery()
        table_configs2 = discovery2.discover()
        
        # Should be in same order
        names1 = [tc.table_name for tc in table_configs]
        names2 = [tc.table_name for tc in table_configs2]
        
        assert names1 == names2, "Config load order should be stable"
