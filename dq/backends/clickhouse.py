"""
ClickHouse backend implementation for the data quality engine.
Connects to a running ClickHouse instance to execute quality checks.
"""

from typing import Dict, List, Optional, Set

import clickhouse_connect
from clickhouse_connect.driver.exceptions import Error as ClickHouseError

from dq.engine import DatabaseBackend


class BackendError(Exception):
    """Raised when backend encounters an error (unknown table/column, etc.)"""
    pass


class ClickHouseBackend(DatabaseBackend):
    """ClickHouse backend for data quality checks"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        username: str = "default",
        password: str = "",
        database: str = "data_quality"
    ):
        """
        Initialize ClickHouse backend
        
        Args:
            host: ClickHouse server host
            port: ClickHouse HTTP port
            username: Database username
            password: Database password
            database: Database name
        """
        self.client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database
        )
        self.host = host
        self.port = port
        self.database = database
        self._table_cache: Dict[str, Set[str]] = {}

    def get_table_columns(self, table_name: str) -> List[str]:
        """
        Get column names for a table from system.columns.
        
        Returns only column names (metadata), never data values.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of column names
            
        Raises:
            BackendError: If table doesn't exist
        """
        return list(self._get_table_columns(table_name))

    def _get_table_columns(self, table_name: str) -> Set[str]:
        """
        Get the set of column names for a table from system.columns.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Set of column names
            
        Raises:
            BackendError: If table doesn't exist
        """
        if table_name in self._table_cache:
            return self._table_cache[table_name]
        
        try:
            result = self.client.query(
                f"SELECT name FROM system.columns WHERE database = '{self.database}' AND table = '{table_name}'"
            )
            columns = {row[0] for row in result.result_rows}
            # If no columns returned, table doesn't exist
            if not columns:
                raise BackendError(f"Unknown table '{table_name}'")
            self._table_cache[table_name] = columns
            return columns
        except ClickHouseError as e:
            # If the query fails for any reason related to the table not existing,
            # raise Unknown table error. Otherwise, raise generic error.
            error_msg = str(e).lower()
            # Check for various error patterns that indicate table doesn't exist
            if any(pattern in error_msg for pattern in ["unknown table", "table doesn't exist", "missing columns", "database error", "unknown database"]):
                raise BackendError(f"Unknown table '{table_name}'")
            else:
                raise BackendError(f"Query execution failed: {type(e).__name__}")

    def _validate_table_and_column(self, table_name: str, column: str) -> None:
        """
        Validate that a table and column exist.
        
        Args:
            table_name: Name of the table
            column: Name of the column
            
        Raises:
            BackendError: If table or column doesn't exist
        """
        columns = self._get_table_columns(table_name)
        if column not in columns:
            raise BackendError(f"Unknown column '{column}' in table '{table_name}'")

    def _execute_query(self, query: str) -> int:
        """
        Execute a COUNT query and return the result
        
        Args:
            query: SQL query that returns a single count
            
        Returns:
            Count as integer
            
        Raises:
            BackendError: If query execution fails
        """
        try:
            result = self.client.query(query)
            return result.first_row[0]
        except ClickHouseError as e:
            # Re-raise with generic message (never include data values)
            raise BackendError(f"Query execution failed: {type(e).__name__}")

    def get_row_count(self, table_name: str) -> int:
        """
        Get total row count for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Total number of rows in the table
        """
        # Validate table exists
        self._get_table_columns(table_name)
        query = f"SELECT count(*) FROM {table_name}"
        return self._execute_query(query)

    def count_null_values(self, table_name: str, column: str) -> int:
        """
        Count NULL values in a column.
        
        Args:
            table_name: Name of the table
            column: Name of the column to check
            
        Returns:
            Count of NULL values in the column
        """
        # Validate table and column exist
        self._validate_table_and_column(table_name, column)
        query = f"SELECT count(*) FROM {table_name} WHERE {column} IS NULL"
        return self._execute_query(query)

    def count_duplicate_keys(
        self,
        table_name: str,
        columns: List[str],
        group_by: Optional[List[str]] = None
    ) -> int:
        """
        Count duplicate key violations.
        
        For each unique key value, if it appears N times, counts N-1 violations.
        If group_by is specified, counts duplicates within each group separately.
        
        Args:
            table_name: Name of the table
            columns: List of column names that form the key
            group_by: Optional list of columns to group by before checking duplicates
            
        Returns:
            Total count of duplicate key violations
        """
        # Validate table and all columns exist
        table_columns = self._get_table_columns(table_name)
        for col in columns:
            if col not in table_columns:
                raise BackendError(f"Unknown column '{col}' in table '{table_name}'")
        if group_by:
            for col in group_by:
                if col not in table_columns:
                    raise BackendError(f"Unknown column '{col}' in table '{table_name}'")
        
        columns_str = ", ".join(columns)
        
        if group_by:
            # Count duplicates within each group
            group_by_str = ", ".join(group_by)
            query = f"""
                SELECT sum(duplicates) FROM (
                    SELECT 
                        {group_by_str},
                        count(*) - 1 as duplicates
                    FROM {table_name}
                    GROUP BY {group_by_str}, {columns_str}
                    HAVING count(*) > 1
                )
            """
        else:
            # Count duplicates globally
            query = f"""
                SELECT sum(duplicates) FROM (
                    SELECT 
                        {columns_str},
                        count(*) - 1 as duplicates
                    FROM {table_name}
                    GROUP BY {columns_str}
                    HAVING count(*) > 1
                )
            """
        
        return self._execute_query(query)

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
        
        A violation occurs when a row in table_name references a row in
        referenced_table, but their tenant_column values don't match.
        NULL tenant_column values are not counted as violations (they are caught
        by null checks instead).
        
        Args:
            table_name: Name of the table with the foreign key
            column: Column name in table_name that references the other table
            referenced_table: Name of the referenced table
            referenced_column: Column name in referenced_table that is referenced
            tenant_column: Column name that stores the tenant ID in both tables
            
        Returns:
            Count of cross-tenant reference violations
        """
        # Validate tables and columns exist
        table_columns = self._get_table_columns(table_name)
        if column not in table_columns:
            raise BackendError(f"Unknown column '{column}' in table '{table_name}'")
        if tenant_column not in table_columns:
            raise BackendError(f"Unknown column '{tenant_column}' in table '{table_name}'")
        
        ref_columns = self._get_table_columns(referenced_table)
        if referenced_column not in ref_columns:
            raise BackendError(f"Unknown column '{referenced_column}' in table '{referenced_table}'")
        if tenant_column not in ref_columns:
            raise BackendError(f"Unknown column '{tenant_column}' in table '{referenced_table}'")
        
        query = f"""
            SELECT count(*)
            FROM {table_name} t1
            INNER JOIN {referenced_table} t2 ON t1.{column} = t2.{referenced_column}
            WHERE t1.{tenant_column} != t2.{tenant_column}
              AND t1.{tenant_column} IS NOT NULL
              AND t2.{tenant_column} IS NOT NULL
        """
        return self._execute_query(query)

    def count_range_violations(
        self,
        table_name: str,
        column: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None
    ) -> int:
        """
        Count values outside specified range.
        
        NULL values are not counted as violations (they are caught by null checks).
        
        Args:
            table_name: Name of the table
            column: Column name to check
            min_value: Minimum allowed value (inclusive), or None for no lower bound
            max_value: Maximum allowed value (inclusive), or None for no upper bound
            
        Returns:
            Count of values outside the specified range
        """
        # Validate table and column exist
        self._validate_table_and_column(table_name, column)
        
        conditions = []
        if min_value is not None:
            conditions.append(f"{column} < {min_value}")
        if max_value is not None:
            conditions.append(f"{column} > {max_value}")
        
        if not conditions:
            return 0
        
        where_clause = " AND ".join(conditions)
        query = f"SELECT count(*) FROM {table_name} WHERE {where_clause} AND {column} IS NOT NULL"
        return self._execute_query(query)

    def close(self):
        """Close the database connection"""
        if self.client:
            self.client.close()
