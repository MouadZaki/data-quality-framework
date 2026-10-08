"""
ClickHouse backend implementation for the data quality engine.
Connects to a running ClickHouse instance to execute quality checks.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import clickhouse_connect
from dq.engine import DatabaseBackend


class ClickHouseBackend(DatabaseBackend):
    """ClickHouse backend for data quality checks"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        username: str = "default",
        password: str = "",
        database: str = "default"
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

    def _execute_query(self, query: str) -> int:
        """
        Execute a COUNT query and return the result
        
        Args:
            query: SQL query that returns a single count
            
        Returns:
            Count as integer
        """
        result = self.client.query(query)
        # ClickHouse returns result as list of lists
        return result.first_row[0]

    def get_row_count(self, table_name: str) -> int:
        """Get total row count for a table"""
        query = f"SELECT count(*) FROM {table_name}"
        return self._execute_query(query)

    def count_null_values(self, table_name: str, column: str) -> int:
        """Count NULL values in a column"""
        query = f"SELECT count(*) FROM {table_name} WHERE {column} IS NULL"
        return self._execute_query(query)

    def count_duplicate_keys(
        self,
        table_name: str,
        columns: List[str],
        group_by: Optional[List[str]] = None
    ) -> int:
        """Count duplicate key violations"""
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
        """Count cross-tenant reference violations"""
        query = f"""
            SELECT count(*)
            FROM {table_name} t1
            INNER JOIN {referenced_table} t2 ON t1.{column} = t2.{referenced_column}
            WHERE t1.{tenant_column} != t2.{tenant_column}
        """
        return self._execute_query(query)

    def count_range_violations(
        self,
        table_name: str,
        column: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None
    ) -> int:
        """Count values outside specified range"""
        conditions = []
        if min_value is not None:
            conditions.append(f"{column} < {min_value}")
        if max_value is not None:
            conditions.append(f"{column} > {max_value}")
        
        if not conditions:
            return 0
        
        where_clause = " OR ".join(conditions)
        query = f"SELECT count(*) FROM {table_name} WHERE {where_clause}"
        return self._execute_query(query)

    def close(self):
        """Close the database connection"""
        if self.client:
            self.client.close()
