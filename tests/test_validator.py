"""
Tests for configuration validator.
Tests use temporary directories, never the real configs.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from dq.validate import ConfigValidator, ValidationError


class TestConfigValidator:
    """Test configuration validator"""

    @pytest.fixture
    def temp_configs_dir(self):
        """Create a temporary directory for config files"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    def test_valid_config(self, temp_configs_dir):
        """Test that a valid config passes validation"""
        config_file = temp_configs_dir / "accounts.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_id_unique_per_org
    type: unique_key
    config:
      columns: ["id"]
      group_by: ["organisation_id"]
  - name: account_org_id_not_null
    type: null_check
    config:
      column: organisation_id
      severity: ERROR
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is True
        assert len(validator.errors) == 0

    def test_invalid_yaml(self, temp_configs_dir):
        """Test that invalid YAML is caught"""
        config_file = temp_configs_dir / "invalid.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_id_unique
    type: unique_key
    config:
      columns: ["id"
      # Missing closing bracket
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("Invalid YAML" in error.message for error in validator.errors)

    def test_invalid_check_type(self, temp_configs_dir):
        """Test that invalid check type is caught"""
        config_file = temp_configs_dir / "invalid_type.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_check
    type: invalid_check_type
    config:
      column: id
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("Invalid check type" in error.message for error in validator.errors)

    def test_missing_required_field_table_name(self, temp_configs_dir):
        """Test that missing table_name is caught"""
        config_file = temp_configs_dir / "missing_table.yml"
        config_file.write_text("""
tenant_column: organisation_id
checks:
  - name: account_check
    type: null_check
    config:
      column: id
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("Missing required field: table_name" in error.message for error in validator.errors)

    def test_missing_required_field_checks(self, temp_configs_dir):
        """Test that missing checks field is caught"""
        config_file = temp_configs_dir / "missing_checks.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("Missing required field: checks" in error.message for error in validator.errors)

    def test_missing_required_field_name(self, temp_configs_dir):
        """Test that missing check name is caught"""
        config_file = temp_configs_dir / "missing_name.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - type: null_check
    config:
      column: id
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("missing required field 'name'" in error.message for error in validator.errors)

    def test_missing_required_field_type(self, temp_configs_dir):
        """Test that missing check type is caught"""
        config_file = temp_configs_dir / "missing_type.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_check
    config:
      column: id
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("Missing required field: type" in error.message for error in validator.errors)

    def test_duplicate_table_name(self, temp_configs_dir):
        """Test that duplicate table names are caught"""
        config_file1 = temp_configs_dir / "accounts1.yml"
        config_file1.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_check
    type: null_check
    config:
      column: id
""")
        
        config_file2 = temp_configs_dir / "accounts2.yml"
        config_file2.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: other_check
    type: null_check
    config:
      column: id
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("Duplicate table name" in error.message for error in validator.errors)

    def test_duplicate_check_name_within_table(self, temp_configs_dir):
        """Test that duplicate check names within a table are caught"""
        config_file = temp_configs_dir / "accounts.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_check
    type: null_check
    config:
      column: id
  - name: account_check
    type: unique_key
    config:
      columns: ["id"]
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("Duplicate check name" in error.message for error in validator.errors)

    def test_cross_tenant_check_references_nonexistent_table(self, temp_configs_dir):
        """Test that cross-tenant check referencing nonexistent table is caught"""
        config_file = temp_configs_dir / "holdings.yml"
        config_file.write_text("""
table_name: holdings
tenant_column: organisation_id
checks:
  - name: holding_portfolio_cross_tenant
    type: cross_tenant_check
    config:
      column: portfolio_id
      referenced_table: portfolios
      referenced_column: id
      severity: ERROR
""")
        
        # No portfolios.yml file, so the referenced table doesn't exist in configs
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("not defined in any config file" in error.message for error in validator.errors)

    def test_check_on_nonexistent_column(self, temp_configs_dir):
        """Test that check on nonexistent column is caught"""
        config_file = temp_configs_dir / "accounts.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_invalid_column_check
    type: null_check
    config:
      column: nonexistent_column
      severity: ERROR
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("does not exist in table" in error.message for error in validator.errors)

    def test_tenant_owned_table_without_tenant_column(self, temp_configs_dir):
        """Test that tenant-owned table without tenant column is caught"""
        config_file = temp_configs_dir / "accounts.yml"
        config_file.write_text("""
table_name: accounts
checks:
  - name: account_check
    type: null_check
    config:
      column: id
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("has no tenant_column defined" in error.message for error in validator.errors)

    def test_row_count_reconciliation_non_positive_expected_count(self, temp_configs_dir):
        """Test that row_count_reconciliation with non-positive expected count is caught"""
        config_file = temp_configs_dir / "organisations.yml"
        config_file.write_text("""
table_name: organisations
checks:
  - name: org_row_count
    type: row_count_reconciliation
    config:
      expected_count: 0
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("must be a positive integer" in error.message for error in validator.errors)

    def test_row_count_reconciliation_negative_expected_count(self, temp_configs_dir):
        """Test that row_count_reconciliation with negative expected count is caught"""
        config_file = temp_configs_dir / "organisations.yml"
        config_file.write_text("""
table_name: organisations
checks:
  - name: org_row_count
    type: row_count_reconciliation
    config:
      expected_count: -5
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("must be a positive integer" in error.message for error in validator.errors)

    def test_shared_reference_table_without_tenant_column(self, temp_configs_dir):
        """Test that shared reference table without tenant column is valid"""
        config_file = temp_configs_dir / "securities.yml"
        config_file.write_text("""
table_name: securities
is_shared_reference: true
checks:
  - name: security_symbol_unique
    type: unique_key
    config:
      columns: ["symbol"]
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is True
        assert len(validator.errors) == 0

    def test_null_check_missing_column(self, temp_configs_dir):
        """Test that null_check without column is caught"""
        config_file = temp_configs_dir / "accounts.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_check
    type: null_check
    config:
      severity: ERROR
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("missing required field 'column'" in error.message for error in validator.errors)

    def test_unique_key_missing_columns(self, temp_configs_dir):
        """Test that unique_key without columns is caught"""
        config_file = temp_configs_dir / "accounts.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_check
    type: unique_key
    config:
      group_by: ["organisation_id"]
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("missing required field 'columns'" in error.message for error in validator.errors)

    def test_cross_tenant_check_missing_referenced_table(self, temp_configs_dir):
        """Test that cross_tenant_check without referenced_table is caught"""
        config_file = temp_configs_dir / "holdings.yml"
        config_file.write_text("""
table_name: holdings
tenant_column: organisation_id
checks:
  - name: holding_check
    type: cross_tenant_check
    config:
      column: portfolio_id
      referenced_column: id
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("missing required field 'referenced_table'" in error.message for error in validator.errors)

    def test_range_check_missing_column(self, temp_configs_dir):
        """Test that range_check without column is caught"""
        config_file = temp_configs_dir / "accounts.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_check
    type: range_check
    config:
      min_value: 0
      max_value: 1000000
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        assert any("missing required field 'column'" in error.message for error in validator.errors)

    def test_multiple_errors_reported(self, temp_configs_dir):
        """Test that multiple errors are all reported"""
        config_file = temp_configs_dir / "broken.yml"
        config_file.write_text("""
table_name: accounts
tenant_column: organisation_id
checks:
  - name: account_check
    type: invalid_type
    config:
      column: nonexistent_column
""")
        
        validator = ConfigValidator(configs_dir=str(temp_configs_dir))
        assert validator.validate_all() is False
        # Should have at least 2 errors: invalid type and nonexistent column
        assert len(validator.errors) >= 2


class TestRealConfigsValidation:
    """Test that real configs pass validation"""

    def test_real_configs_are_valid(self):
        """Test that the real configs in configs/ directory are valid"""
        validator = ConfigValidator(configs_dir="configs")
        assert validator.validate_all() is True
        assert len(validator.errors) == 0
