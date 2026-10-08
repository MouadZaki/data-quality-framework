"""
Discovery module walks configs/ and builds executable test objects from YAML declarations.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from typing import List, Dict
from dq.schema import TableConfig, Check


class DiscoveryError(Exception):
    """Raised when discovery fails"""
    pass


class ConfigDiscovery:
    """Discovers and loads table configurations from YAML files"""

    def __init__(self, configs_dir: str = "configs"):
        """
        Initialize discovery with configs directory path
        
        Args:
            configs_dir: Path to directory containing YAML config files
        """
        self.configs_dir = Path(configs_dir)
        if not self.configs_dir.exists():
            raise DiscoveryError(f"Configs directory not found: {configs_dir}")

    def discover(self) -> List[TableConfig]:
        """
        Walk configs/ directory and load all table configurations
        
        Returns:
            List of TableConfig objects parsed from YAML files
        """
        table_configs = []
        
        # Find all .yaml files in configs directory
        yaml_files = list(self.configs_dir.glob("*.yaml"))
        
        if not yaml_files:
            raise DiscoveryError(f"No YAML files found in {self.configs_dir}")
        
        for yaml_file in yaml_files:
            try:
                table_config = self._load_yaml_file(yaml_file)
                table_configs.append(table_config)
            except Exception as e:
                raise DiscoveryError(f"Failed to load {yaml_file}: {e}")
        
        return table_configs

    def _load_yaml_file(self, yaml_path: Path) -> TableConfig:
        """
        Load and parse a single YAML file into a TableConfig
        
        Args:
            yaml_path: Path to YAML file
            
        Returns:
            TableConfig object
        """
        with open(yaml_path, 'r') as f:
            yaml_data = yaml.safe_load(f)
        
        # Validate and parse using Pydantic model
        table_config = TableConfig(**yaml_data)
        
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
