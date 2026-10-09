"""
Discovery module walks configs/ and builds executable test objects from YAML declarations.
"""

from pathlib import Path

import yaml
from typing import List, Dict
from dq.schema import TableConfig, Check, CheckType


class DiscoveryError(Exception):
    """Raised when discovery fails"""
    pass


class ConfigDiscovery:
    """Discovers and loads table configurations from YAML files"""

    def __init__(self, configs_dir: str = "configs"):
        """
        Initialize discovery with configs directory path
        
        Args:
            configs_dir: Path to directory containing YAML config files (relative to project root)
        """
        # Resolve configs directory relative to this file's location (project root)
        project_root = Path(__file__).parent.parent
        self.configs_dir = project_root / configs_dir
        
        if not self.configs_dir.exists():
            raise DiscoveryError(f"Configs directory not found: {self.configs_dir}")

    def discover(self) -> List[TableConfig]:
        """
        Walk configs/ directory and load all table configurations
        
        Returns:
            List of TableConfig objects parsed from YAML files
        """
        table_configs = []
        seen_table_names = set()
        
        # Find all .yaml files in configs directory and sort for stable order
        yaml_files = sorted(self.configs_dir.glob("*.yaml"))
        
        if not yaml_files:
            raise DiscoveryError(f"No YAML files found in {self.configs_dir}")
        
        for yaml_file in yaml_files:
            try:
                table_config = self._load_yaml_file(yaml_file)
                
                # Check for duplicate table names
                if table_config.table_name in seen_table_names:
                    raise DiscoveryError(
                        f"Duplicate table_name '{table_config.table_name}' found in {yaml_file.name}. "
                        f"Table names must be unique across all config files."
                    )
                seen_table_names.add(table_config.table_name)
                
                table_configs.append(table_config)
            except DiscoveryError:
                raise
            except Exception as e:
                raise DiscoveryError(f"Failed to load {yaml_file}: {e}") from e
        
        return table_configs

    def _load_yaml_file(self, yaml_path: Path) -> TableConfig:
        """
        Load and parse a single YAML file into a TableConfig
        
        Args:
            yaml_path: Path to YAML file
            
        Returns:
            TableConfig object
        """
        with open(yaml_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f)
        
        # Check for empty YAML file
        if yaml_data is None:
            raise DiscoveryError(
                f"Empty YAML file: {yaml_path.name}. "
                f"YAML files must contain a valid table configuration."
            )
        
        # Validate and parse using Pydantic model
        try:
            table_config = TableConfig(**yaml_data)
        except Exception as e:
            raise DiscoveryError(
                f"Invalid table configuration in {yaml_path.name}: {e}"
            ) from e
        
        # Check for duplicate check names within this table
        check_names = [check.name for check in table_config.checks]
        if len(check_names) != len(set(check_names)):
            duplicates = [name for name in check_names if check_names.count(name) > 1]
            raise DiscoveryError(
                f"Duplicate check name(s) in {yaml_path.name}: {set(duplicates)}. "
                f"Check names must be unique within a table configuration."
            )
        
        # Validate check types
        for check in table_config.checks:
            try:
                CheckType(check.type)
            except ValueError:
                valid_types = [t.value for t in CheckType]
                raise DiscoveryError(
                    f"Invalid check type '{check.type}' in check '{check.name}' in {yaml_path.name}. "
                    f"Valid types are: {', '.join(valid_types)}"
                ) from None
        
        return table_config

    def get_checks_by_table(self) -> Dict[str, List[Check]]:
        """
        Get all checks grouped by table name
        
        Returns:
            Dictionary mapping table_name to list of Check objects
        """
        table_configs = self.discover()
        checks_by_table = {}
        
        for table_config in table_configs:
            checks_by_table[table_config.table_name] = table_config.checks
        
        return checks_by_table

    def get_all_checks(self) -> List[Check]:
        """
        Get all checks from all tables
        
        Returns:
            List of all Check objects
        """
        table_configs = self.discover()
        all_checks = []
        
        for table_config in table_configs:
            all_checks.extend(table_config.checks)
        
        return all_checks


def main():
    """Main entry point for testing discovery"""
    print("Discovering table configurations...\n")
    
    discovery = ConfigDiscovery()
    table_configs = discovery.discover()
    
    print(f"Found {len(table_configs)} table configurations:\n")
    
    for table_config in table_configs:
        print(f"Table: {table_config.table_name}")
        print(f"  Description: {table_config.description}")
        print(f"  Tenant column: {table_config.tenant_column}")
        print(f"  Shared reference: {table_config.is_shared_reference}")
        print(f"  Checks: {len(table_config.checks)}")
        for check in table_config.checks:
            print(f"    - {check.name} ({check.type})")
        print()


if __name__ == "__main__":
    main()
