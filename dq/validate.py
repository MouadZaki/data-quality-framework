"""
Configuration validator for data quality checks.
Loads all YAML configs and reports validation errors.
"""

import sys
import yaml
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass

from dq.schema import CheckType, TableConfig, Check
from dq.discovery import ConfigDiscovery


@dataclass
class ValidationError:
    """Represents a validation error"""
    file_path: str
    table_name: Optional[str]
    check_name: Optional[str]
    message: str


class ConfigValidator:
    """Validates data quality configuration files"""

    def __init__(self, configs_dir: str = "configs"):
        """
        Initialize validator
        
        Args:
            configs_dir: Directory containing YAML config files
        """
        self.configs_dir = Path(configs_dir)
        self.errors: List[ValidationError] = []
        
        # Load fixture schema for column validation
        self.fixture_schema: Dict[str, Set[str]] = self._load_fixture_schema()
        
        # Store parsed configs for cross-reference validation
        self.parsed_configs: Dict[str, Dict] = {}

    def _load_fixture_schema(self) -> Dict[str, Set[str]]:
        """
        Load column names from fixture generator for schema validation.
        
        Returns:
            Dict mapping table names to sets of column names
        """
        try:
            from fixtures.generator import FixtureGenerator
            generator = FixtureGenerator(verbose=False)
            fixtures = generator.generate()
            
            schema = {}
            # Get column names from each fixture table
            for table_name in [
                "organisations", "advisors", "accounts", "contacts",
                "securities", "portfolios", "holdings", "transactions",
                "trades", "fee_schedules"
            ]:
                table_data = getattr(fixtures, table_name, None)
                if table_data and len(table_data) > 0:
                    # Get column names from first row
                    import dataclasses
                    if dataclasses.is_dataclass(table_data[0]):
                        schema[table_name] = set(table_data[0].__dataclass_fields__.keys())
            
            return schema
        except Exception:
            # If fixtures can't be loaded, return empty schema
            # Column validation will be skipped
            return {}

    def validate_all(self) -> bool:
        """
        Validate all configuration files.
        
        Returns:
            True if all configs are valid, False otherwise
        """
        self.errors = []
        
        if not self.configs_dir.exists():
            self.errors.append(ValidationError(
                file_path=str(self.configs_dir),
                table_name=None,
                check_name=None,
                message=f"Configs directory does not exist: {self.configs_dir}"
            ))
            return False
        
        # Find all YAML files
        yaml_files = list(self.configs_dir.glob("*.yml")) + list(self.configs_dir.glob("*.yaml"))
        
        if not yaml_files:
            self.errors.append(ValidationError(
                file_path=str(self.configs_dir),
                table_name=None,
                check_name=None,
                message="No YAML config files found"
            ))
            return False
        
        # Track table names for duplicate detection
        table_names: Set[str] = set()
        
        # Parse and validate each file
        for yaml_file in yaml_files:
            self._validate_yaml_file(yaml_file, table_names)
        
        # Validate cross-tenant references after all tables are loaded
        self._validate_cross_tenant_references()
        
        # Validate tenant columns
        self._validate_tenant_column()
        
        return len(self.errors) == 0

    def _validate_yaml_file(self, yaml_file: Path, table_names: Set[str]) -> None:
        """
        Validate a single YAML configuration file.
        
        Args:
            yaml_file: Path to YAML file
            table_names: Set of already-seen table names (for duplicate detection)
        """
        try:
            with open(yaml_file, 'r') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=None,
                check_name=None,
                message=f"Invalid YAML: {str(e)}"
            ))
            return
        
        if data is None:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=None,
                check_name=None,
                message="File is empty or contains no data"
            ))
            return
        
        # Check for required fields
        if 'table_name' not in data:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=None,
                check_name=None,
                message="Missing required field: table_name"
            ))
            return
        
        table_name = data['table_name']
        
        # Store parsed config for later validation
        self.parsed_configs[table_name] = data
        
        # Check for duplicate table name
        if table_name in table_names:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=None,
                message=f"Duplicate table name: '{table_name}' already defined in another config"
            ))
        table_names.add(table_name)
        
        # Validate checks
        if 'checks' not in data:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=None,
                message="Missing required field: checks"
            ))
            return
        
        checks = data.get('checks', [])
        if not isinstance(checks, list):
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=None,
                message="Field 'checks' must be a list"
            ))
            return
        
        # Track check names for duplicate detection within table
        check_names: Set[str] = set()
        
        for i, check_data in enumerate(checks):
            self._validate_check(yaml_file, table_name, check_data, i, check_names)

    def _validate_check(
        self,
        yaml_file: Path,
        table_name: str,
        check_data: Dict,
        index: int,
        check_names: Set[str]
    ) -> None:
        """
        Validate a single check configuration.
        
        Args:
            yaml_file: Path to YAML file
            table_name: Name of the table
            check_data: Check configuration dict
            index: Index of check in list (for error messages)
            check_names: Set of already-seen check names in this table
        """
        if not isinstance(check_data, dict):
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=None,
                message=f"Check at index {index} must be a dict"
            ))
            return
        
        # Check for required fields
        if 'name' not in check_data:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=None,
                message=f"Check at index {index}: missing required field 'name'"
            ))
            return
        
        check_name = check_data['name']
        
        # Check for duplicate check name within table
        if check_name in check_names:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message=f"Duplicate check name: '{check_name}' already defined in this table"
            ))
        check_names.add(check_name)
        
        if 'type' not in check_data:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message="Missing required field: type"
            ))
            return
        
        check_type_str = check_data['type']
        
        # Validate check type
        check_type = None
        try:
            check_type = CheckType(check_type_str)
        except ValueError:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message=f"Invalid check type: '{check_type_str}'. Valid types: {[t.value for t in CheckType]}"
            ))
            # Don't return - continue to validate other fields
        
        # Validate config based on check type
        config = check_data.get('config', {})
        if not isinstance(config, dict):
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message="Field 'config' must be a dict"
            ))
            return
        
        # Type-specific validation (only if check type is valid)
        if check_type == CheckType.NULL_CHECK:
            self._validate_null_check(yaml_file, table_name, check_name, config)
        elif check_type == CheckType.UNIQUE_KEY:
            self._validate_unique_key(yaml_file, table_name, check_name, config)
        elif check_type == CheckType.CROSS_TENANT_CHECK:
            self._validate_cross_tenant_check(yaml_file, table_name, check_name, config)
        elif check_type == CheckType.ROW_COUNT_RECONCILIATION:
            self._validate_row_count_reconciliation(yaml_file, table_name, check_name, config)
        elif check_type == CheckType.RANGE_CHECK:
            self._validate_range_check(yaml_file, table_name, check_name, config)
        else:
            # Even if check type is invalid, validate column if present
            if 'column' in config:
                self._validate_column_exists(yaml_file, table_name, check_name, config['column'])

    def _validate_null_check(self, yaml_file: Path, table_name: str, check_name: str, config: Dict) -> None:
        """Validate null_check configuration"""
        if 'column' not in config:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message="null_check: missing required field 'column' in config"
            ))
            return
        
        column = config['column']
        self._validate_column_exists(yaml_file, table_name, check_name, column)

    def _validate_unique_key(self, yaml_file: Path, table_name: str, check_name: str, config: Dict) -> None:
        """Validate unique_key configuration"""
        if 'columns' not in config:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message="unique_key: missing required field 'columns' in config"
            ))
            return
        
        columns = config['columns']
        if not isinstance(columns, list):
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message="unique_key: field 'columns' must be a list"
            ))
            return
        
        for column in columns:
            self._validate_column_exists(yaml_file, table_name, check_name, column)

    def _validate_cross_tenant_check(self, yaml_file: Path, table_name: str, check_name: str, config: Dict) -> None:
        """Validate cross_tenant_check configuration"""
        required_fields = ['column', 'referenced_table', 'referenced_column']
        for field in required_fields:
            if field not in config:
                self.errors.append(ValidationError(
                    file_path=str(yaml_file),
                    table_name=table_name,
                    check_name=check_name,
                    message=f"cross_tenant_check: missing required field '{field}' in config"
                ))
        
        # Validate column exists in source table
        if 'column' in config:
            self._validate_column_exists(yaml_file, table_name, check_name, config['column'])

    def _validate_row_count_reconciliation(self, yaml_file: Path, table_name: str, check_name: str, config: Dict) -> None:
        """Validate row_count_reconciliation configuration"""
        if 'expected_count' not in config:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message="row_count_reconciliation: missing required field 'expected_count' in config"
            ))
            return
        
        expected_count = config['expected_count']
        if not isinstance(expected_count, int) or expected_count <= 0:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message=f"row_count_reconciliation: 'expected_count' must be a positive integer, got {expected_count}"
            ))

    def _validate_range_check(self, yaml_file: Path, table_name: str, check_name: str, config: Dict) -> None:
        """Validate range_check configuration"""
        if 'column' not in config:
            self.errors.append(ValidationError(
                file_path=str(yaml_file),
                table_name=table_name,
                check_name=check_name,
                message="range_check: missing required field 'column' in config"
            ))
            return
        
        column = config['column']
        self._validate_column_exists(yaml_file, table_name, check_name, column)

    def _validate_column_exists(self, yaml_file: Path, table_name: str, check_name: str, column: str) -> None:
        """
        Validate that a column exists in the fixture schema.
        
        Args:
            yaml_file: Path to YAML file
            table_name: Name of the table
            check_name: Name of the check
            column: Column name to validate
        """
        if table_name in self.fixture_schema:
            if column not in self.fixture_schema[table_name]:
                self.errors.append(ValidationError(
                    file_path=str(yaml_file),
                    table_name=table_name,
                    check_name=check_name,
                    message=f"Column '{column}' does not exist in table '{table_name}'"
                ))

    def _validate_cross_tenant_references(self) -> None:
        """
        Validate that all cross-tenant checks reference tables that exist in configs.
        This must be done after all configs are loaded.
        """
        # Use the parsed configs we stored during validation
        table_names = set(self.parsed_configs.keys())
        
        for table_name, data in self.parsed_configs.items():
            checks = data.get('checks', [])
            
            for check_data in checks:
                if check_data.get('type') == CheckType.CROSS_TENANT_CHECK.value:
                    config = check_data.get('config', {})
                    referenced_table = config.get('referenced_table')
                    
                    if referenced_table and referenced_table not in table_names:
                        # Find the file for this table
                        yaml_files = list(self.configs_dir.glob("*.yml")) + list(self.configs_dir.glob("*.yaml"))
                        for yaml_file in yaml_files:
                            try:
                                with open(yaml_file, 'r') as f:
                                    file_data = yaml.safe_load(f)
                                if file_data and file_data.get('table_name') == table_name:
                                    self.errors.append(ValidationError(
                                        file_path=str(yaml_file),
                                        table_name=table_name,
                                        check_name=check_data.get('name'),
                                        message=f"cross_tenant_check references table '{referenced_table}' which is not defined in any config file"
                                    ))
                                    break
                            except yaml.YAMLError:
                                pass

    def _validate_tenant_column(self) -> None:
        """
        Validate that tenant-owned tables have a tenant column defined.
        """
        for table_name, data in self.parsed_configs.items():
            # A table is tenant-owned if it's not a shared reference
            is_shared_reference = data.get('is_shared_reference', False)
            
            if not is_shared_reference:
                # If it's not a shared reference, it should have a tenant column
                tenant_column = data.get('tenant_column')
                if tenant_column is None:
                    # Find the file for this table
                    yaml_files = list(self.configs_dir.glob("*.yml")) + list(self.configs_dir.glob("*.yaml"))
                    for yaml_file in yaml_files:
                        try:
                            with open(yaml_file, 'r') as f:
                                file_data = yaml.safe_load(f)
                            if file_data and file_data.get('table_name') == table_name:
                                self.errors.append(ValidationError(
                                    file_path=str(yaml_file),
                                    table_name=table_name,
                                    check_name=None,
                                    message=f"Table '{table_name}' is not a shared reference but has no tenant_column defined"
                                ))
                                break
                        except yaml.YAMLError:
                            pass

    def print_errors(self) -> None:
        """Print all validation errors to stdout"""
        if not self.errors:
            print("✓ All configurations are valid")
            return
        
        print(f"✗ Found {len(self.errors)} validation error(s):")
        print()
        
        for error in self.errors:
            print(f"File: {error.file_path}")
            if error.table_name:
                print(f"  Table: {error.table_name}")
            if error.check_name:
                print(f"  Check: {error.check_name}")
            print(f"  Error: {error.message}")
            print()


def main():
    """Main entry point for validator CLI"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate data quality configuration files")
    parser.add_argument(
        '--configs-dir',
        default='configs',
        help='Directory containing YAML config files (default: configs)'
    )
    
    args = parser.parse_args()
    
    validator = ConfigValidator(configs_dir=args.configs_dir)
    is_valid = validator.validate_all()
    
    validator.print_errors()
    
    sys.exit(0 if is_valid else 1)


if __name__ == '__main__':
    main()
