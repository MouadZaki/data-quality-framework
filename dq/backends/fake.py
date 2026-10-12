"""
Fake in-memory database backend for unit testing.
Uses fixture data without requiring a database connection.
"""

from typing import Dict, List, Any, Optional
from collections import defaultdict
from dataclasses import asdict

from dq.engine import DatabaseBackend


class BackendError(Exception):
    """Raised when backend operation fails"""
    pass


class FakeBackend(DatabaseBackend):
    """In-memory backend using fixture data for unit testing"""

    def __init__(self, fixtures):
        """
        Initialize with fixture data
        
        Args:
            fixtures: Fixtures object from fixtures.generator
        """
        self.data = self._convert_fixtures_to_dict(fixtures)

    def _convert_fixtures_to_dict(self, fixtures) -> Dict[str, List[Dict]]:
        """Convert fixture dataclasses to dictionary format for querying using asdict"""
        data = {
            "organisations": [asdict(org) for org in fixtures.organisations],
            "advisors": [asdict(advisor) for advisor in fixtures.advisors],
            "accounts": [asdict(account) for account in fixtures.accounts],
            "contacts": [asdict(contact) for contact in fixtures.contacts],
            "securities": [asdict(security) for security in fixtures.securities],
            "portfolios": [asdict(portfolio) for portfolio in fixtures.portfolios],
            "holdings": [asdict(holding) for holding in fixtures.holdings],
            "transactions": [asdict(transaction) for transaction in fixtures.transactions],
            "trades": [asdict(trade) for trade in fixtures.trades],
            "fee_schedules": [asdict(fee_schedule) for fee_schedule in fixtures.fee_schedules]
        }
        return data

    def get_row_count(self, table_name: str) -> int:
        """
        Get total row count for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Total number of rows in the table
            
        Raises:
            BackendError: If table does not exist
        """
        if table_name not in self.data:
            raise BackendError(f"Unknown table: {table_name}")
        return len(self.data[table_name])

    def count_null_values(self, table_name: str, column: str) -> int:
        """
        Count NULL values in a column.
        
        Args:
            table_name: Name of the table
            column: Column name to check for NULL values
            
        Returns:
            Count of NULL values in the column
            
        Raises:
            BackendError: If table does not exist
        """
        if table_name not in self.data:
            raise BackendError(f"Unknown table: {table_name}")
        table_data = self.data[table_name]
        null_count = 0
        for row in table_data:
            if row.get(column) is None:
                null_count += 1
        return null_count

    def count_duplicate_keys(
        self,
        table_name: str,
        columns: List[str],
        group_by: Optional[List[str]] = None
    ) -> int:
        """
        Count duplicate key violations.
        
        A duplicate key violation occurs when the same key value appears more than once.
        If group_by is specified, counts duplicates within each group separately.
        The count returned is the total number of duplicate occurrences (count - 1 for each duplicate key).
        
        Args:
            table_name: Name of the table
            columns: List of column names that form the key
            group_by: Optional list of columns to group by before checking duplicates
            
        Returns:
            Total count of duplicate key violations
            
        Raises:
            BackendError: If table does not exist
        """
        if table_name not in self.data:
            raise BackendError(f"Unknown table: {table_name}")
        table_data = self.data[table_name]
        
        if group_by:
            # Count duplicates within each group
            group_keys = defaultdict(list)
            for row in table_data:
                group_key = tuple(row.get(col) for col in group_by)
                key_value = tuple(row.get(col) for col in columns)
                group_keys[group_key].append(key_value)
            
            duplicate_count = 0
            for group_key, key_values in group_keys.items():
                seen = set()
                for key_value in key_values:
                    if key_value in seen:
                        duplicate_count += 1
                    seen.add(key_value)
            return duplicate_count
        else:
            # Count duplicates globally
            key_counts = defaultdict(int)
            for row in table_data:
                key_value = tuple(row.get(col) for col in columns)
                key_counts[key_value] += 1
            
            duplicate_count = sum(count - 1 for count in key_counts.values() if count > 1)
            return duplicate_count

    def count_cross_tenant_violations(
        self,
        table_name: str,
        column: str,
        referenced_table: str,
        referenced_column: str,
        tenant_column: str
    ) -> int:
        """
        Count cross-tenant reference violations.
        
        A cross-tenant violation occurs when a row in table_name references a row in
        referenced_table via column/referenced_column, but the two rows have different
        tenant_column values. Rows with NULL tenant_column or NULL reference are not counted.
        
        Args:
            table_name: Name of the table containing the reference
            column: Column in table_name that references the other table
            referenced_table: Name of the table being referenced
            referenced_column: Column in referenced_table that is referenced
            tenant_column: Column name containing the tenant identifier
            
        Returns:
            Count of cross-tenant reference violations
            
        Raises:
            BackendError: If table does not exist
        """
        if table_name not in self.data:
            raise BackendError(f"Unknown table: {table_name}")
        if referenced_table not in self.data:
            raise BackendError(f"Unknown referenced table: {referenced_table}")
        
        table_data = self.data[table_name]
        ref_data = self.data[referenced_table]
        
        # Build map: referenced_column -> tenant_column
        ref_tenant_map = {}
        for row in ref_data:
            ref_key = row.get(referenced_column)
            ref_tenant = row.get(tenant_column)
            if ref_key is not None:
                ref_tenant_map[ref_key] = ref_tenant
        
        violation_count = 0
        for row in table_data:
            ref_key = row.get(column)
            row_tenant = row.get(tenant_column)
            
            if ref_key is not None and row_tenant is not None:
                if ref_key in ref_tenant_map:
                    ref_tenant = ref_tenant_map[ref_key]
                    if ref_tenant != row_tenant:
                        violation_count += 1
        
        return violation_count

    def count_range_violations(
        self,
        table_name: str,
        column: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None
    ) -> int:
        """
        Count values outside specified range.
        
        A range violation occurs when a value is less than min_value or greater than max_value.
        NULL values are not counted as violations.
        
        Args:
            table_name: Name of the table
            column: Column name to check
            min_value: Minimum allowed value (inclusive), None means no lower bound
            max_value: Maximum allowed value (inclusive), None means no upper bound
            
        Returns:
            Count of values outside the specified range
            
        Raises:
            BackendError: If table does not exist
        """
        if table_name not in self.data:
            raise BackendError(f"Unknown table: {table_name}")
        table_data = self.data[table_name]
        violation_count = 0
        
        for row in table_data:
            value = row.get(column)
            if value is None:
                continue
            
            if min_value is not None and value < min_value:
                violation_count += 1
            if max_value is not None and value > max_value:
                violation_count += 1
        
        return violation_count
