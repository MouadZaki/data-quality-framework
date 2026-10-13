"""
Auto-generation of tenant-related data quality checks.

This module automatically generates null checks on tenant columns and
cross-tenant checks for foreign-key-style columns in tenant-owned tables.

Naming Convention:
- Foreign key columns ending in _id map to tables by converting to plural:
  - portfolio_id → portfolios
  - account_id → accounts
  - advisor_id → advisors
  - security_id → securities
  - organisation_id → organisations
  - etc.
- Shared reference tables (like securities) are excluded from auto-generation
"""

from typing import List, Dict, Set, Optional
from dq.schema import TableConfig, Check, CheckType, Severity
from dq.engine import DatabaseBackend


# Shared reference tables that should not get auto-generated tenant checks
SHARED_REFERENCE_TABLES = {
    "securities",  # Shared across all tenants
}


def _singular_to_plural(singular: str) -> str:
    """
    Convert a singular table name to its plural form.
    
    Simple heuristic: add 's' if not already ending with 's'.
    Handles common irregular plurals for this project.
    
    Args:
        singular: Singular table name
        
    Returns:
        Plural table name
    """
    # Handle irregular plurals specific to this project
    irregular_plurals = {
        "security": "securities",
    }
    
    if singular in irregular_plurals:
        return irregular_plurals[singular]
    
    if singular.endswith('s'):
        return singular
    return singular + 's'


def _infer_referenced_table(column_name: str) -> str:
    """
    Infer the referenced table name from a foreign key column name.
    
    Args:
        column_name: Column name ending with _id
        
    Returns:
        Inferred table name (plural form)
        
    Examples:
        portfolio_id → portfolios
        account_id → accounts
        security_id → securities
    """
    if not column_name.endswith('_id'):
        raise ValueError(f"Column '{column_name}' does not end with '_id'")
    
    singular = column_name[:-3]  # Remove '_id' suffix
    return _singular_to_plural(singular)


def _is_tenant_owned_table(table_config: TableConfig) -> bool:
    """
    Determine if a table is tenant-owned.
    
    A table is tenant-owned if:
    - It has a tenant_column defined (not None)
    - It is not marked as a shared reference table
    
    Args:
        table_config: Table configuration
        
    Returns:
        True if tenant-owned, False otherwise
    """
    return table_config.tenant_column is not None and not table_config.is_shared_reference


def _get_existing_checks_by_type_and_column(
    table_config: TableConfig
) -> Dict[tuple, Check]:
    """
    Get existing checks indexed by (check_type, column) tuple.
    
    Args:
        table_config: Table configuration
        
    Returns:
        Dictionary mapping (check_type, column) to the check
    """
    existing = {}
    for check in table_config.checks:
        if check.type in [CheckType.NULL_CHECK, CheckType.CROSS_TENANT_CHECK]:
            column = check.config.get("column")
            if column:
                existing[(check.type, column)] = check
    return existing


def get_table_columns_from_backend(backend: DatabaseBackend, table_name: str) -> Set[str]:
    """
    Get column names for a table from the backend.
    
    Uses the backend's get_table_columns method which returns only metadata.
    
    Args:
        backend: Database backend
        table_name: Name of the table
        
    Returns:
        Set of column names
    """
    try:
        columns = backend.get_table_columns(table_name)
        return set(columns)
    except Exception:
        # If backend doesn't support it or table doesn't exist, return empty set
        return set()


def generate_null_check(
    table_name: str,
    tenant_column: str,
    existing_checks: Dict[tuple, Check]
) -> Optional[Check]:
    """
    Generate a null check for the tenant column if not already present.
    
    Args:
        table_name: Name of the table
        tenant_column: Name of the tenant column
        existing_checks: Dictionary of existing checks by (type, column)
        
    Returns:
        Check object or None if already exists
    """
    key = (CheckType.NULL_CHECK, tenant_column)
    if key in existing_checks:
        return None
    
    return Check(
        name=f"auto_{tenant_column}_not_null",
        type=CheckType.NULL_CHECK,
        config={
            "column": tenant_column,
            "severity": "ERROR"
        },
        description=f"Auto-generated: Ensure {tenant_column} is not NULL",
        enabled=True
    )


def generate_cross_tenant_checks(
    table_name: str,
    table_config: TableConfig,
    all_table_configs: List[TableConfig],
    existing_checks: Dict[tuple, Check],
    table_columns: Set[str]
) -> List[Check]:
    """
    Generate cross-tenant checks for foreign-key-style columns.
    
    Args:
        table_name: Name of the table
        table_config: Configuration for the table
        all_table_configs: All table configurations (to look up referenced tables)
        existing_checks: Dictionary of existing checks by (type, column)
        table_columns: Set of actual column names in the table
        
    Returns:
        List of generated Check objects
    """
    if not table_config.tenant_column:
        return []
    
    # Build set of all tenant-owned table names
    tenant_owned_tables = {
        tc.table_name for tc in all_table_configs
        if _is_tenant_owned_table(tc)
    }
    
    # Find all foreign key columns (ending in _id)
    potential_fk_columns = {col for col in table_columns if col.endswith('_id')}
    
    # Exclude the tenant column itself
    if table_config.tenant_column in potential_fk_columns:
        potential_fk_columns.remove(table_config.tenant_column)
    
    generated_checks = []
    
    for fk_column in potential_fk_columns:
        # Infer referenced table
        try:
            referenced_table = _infer_referenced_table(fk_column)
        except ValueError:
            continue
        
        # Skip if referenced table is a shared reference table
        if referenced_table in SHARED_REFERENCE_TABLES:
            continue
        
        # Skip if referenced table is not tenant-owned
        if referenced_table not in tenant_owned_tables:
            continue
        
        # Check if cross-tenant check already exists for this column
        key = (CheckType.CROSS_TENANT_CHECK, fk_column)
        if key in existing_checks:
            continue
        
        # Generate the check
        generated_checks.append(Check(
            name=f"auto_{fk_column}_cross_tenant",
            type=CheckType.CROSS_TENANT_CHECK,
            config={
                "column": fk_column,
                "referenced_table": referenced_table,
                "referenced_column": "id",
                "severity": "ERROR"
            },
            description=f"Auto-generated: Ensure {fk_column} references stay within tenant",
            enabled=True
        ))
    
    return generated_checks


def generate_checks(
    table_configs: List[TableConfig],
    backend: Optional[DatabaseBackend] = None
) -> List[TableConfig]:
    """
    Generate auto-generated checks for all tenant-owned tables.
    
    Args:
        table_configs: List of existing table configurations
        backend: Optional database backend to query for actual schema
    
    Returns:
        New list of table configurations with auto-generated checks added
    """
    new_configs = []
    
    for table_config in table_configs:
        # Skip shared reference tables
        if not _is_tenant_owned_table(table_config):
            new_configs.append(table_config)
            continue
        
        # Get actual column names from backend if available
        table_columns = set()
        if backend:
            table_columns = get_table_columns_from_backend(backend, table_config.table_name)
        
        # If no backend, infer columns from existing checks
        if not table_columns:
            for check in table_config.checks:
                if "column" in check.config:
                    table_columns.add(check.config["column"])
                if "columns" in check.config:
                    table_columns.update(check.config["columns"])
        
        # Get existing checks indexed by type and column
        existing_checks = _get_existing_checks_by_type_and_column(table_config)
        
        # Generate null check for tenant column
        null_check = generate_null_check(
            table_config.table_name,
            table_config.tenant_column,
            existing_checks
        )
        
        # Generate cross-tenant checks
        cross_tenant_checks = generate_cross_tenant_checks(
            table_config.table_name,
            table_config,
            table_configs,
            existing_checks,
            table_columns
        )
        
        # Add generated checks to the table config
        new_checks = list(table_config.checks)
        if null_check:
            new_checks.append(null_check)
        new_checks.extend(cross_tenant_checks)
        
        # Create new table config with generated checks
        new_config = TableConfig(
            table_name=table_config.table_name,
            checks=new_checks,
            description=table_config.description,
            tenant_column=table_config.tenant_column,
            is_shared_reference=table_config.is_shared_reference
        )
        
        new_configs.append(new_config)
    
    return new_configs
