"""
Load fixture data into ClickHouse from CSV files.
Creates tables with Nullable columns and loads CSV data, treating empty strings as NULL.
"""

import os
import sys
import csv
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import clickhouse_connect
from clickhouse_connect.driver.exceptions import Error as ClickHouseError


# Table schemas with Nullable columns where needed
TABLE_SCHEMAS = {
    "organisations": """
        CREATE TABLE IF NOT EXISTS organisations (
            id String,
            name String,
            created_at DateTime
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
    "securities": """
        CREATE TABLE IF NOT EXISTS securities (
            id String,
            symbol String,
            name String,
            asset_class String
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
    "advisors": """
        CREATE TABLE IF NOT EXISTS advisors (
            id String,
            organisation_id String,
            name String,
            email String
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
    "accounts": """
        CREATE TABLE IF NOT EXISTS accounts (
            id String,
            organisation_id String,
            advisor_id String,
            account_number String,
            account_type String,
            balance Nullable(Float64)
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
    "contacts": """
        CREATE TABLE IF NOT EXISTS contacts (
            id String,
            organisation_id Nullable(String),
            account_id String,
            name String,
            email String,
            phone String
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
    "portfolios": """
        CREATE TABLE IF NOT EXISTS portfolios (
            id String,
            organisation_id String,
            account_id String,
            name String
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
    "holdings": """
        CREATE TABLE IF NOT EXISTS holdings (
            id String,
            organisation_id String,
            portfolio_id String,
            security_id String,
            quantity Float64,
            avg_cost Float64
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
    "transactions": """
        CREATE TABLE IF NOT EXISTS transactions (
            id String,
            organisation_id String,
            account_id String,
            transaction_type String,
            amount Float64,
            transaction_date DateTime
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
    "trades": """
        CREATE TABLE IF NOT EXISTS trades (
            id String,
            organisation_id String,
            account_id String,
            security_id String,
            quantity Float64,
            price Float64,
            trade_date DateTime
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
    "fee_schedules": """
        CREATE TABLE IF NOT EXISTS fee_schedules (
            id String,
            organisation_id String,
            fee_type String,
            rate Float64,
            min_fee Float64
        ) ENGINE = MergeTree()
        ORDER BY id
    """,
}


def load_csv_with_null_handling(client, table_name, csv_path):
    """
    Load CSV file into ClickHouse table, treating empty strings as NULL.
    
    This works by:
    1. Reading the CSV file with Python's csv module
    2. Converting empty strings to None (which becomes NULL in ClickHouse)
    3. Parsing datetime columns to Python datetime objects
    4. Using clickhouse_connect's insert with column names and data
    """
    if not os.path.exists(csv_path):
        print(f"Warning: CSV file not found: {csv_path}")
        return
    
    print(f"Loading {table_name} from {csv_path}...")
    
    # Read CSV and convert empty strings to None
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)  # Get column names
        data = []
        for row in reader:
            # Convert empty strings to None for NULL handling
            processed_row = []
            for i, val in enumerate(row):
                if val == '':
                    processed_row.append(None)
                elif headers[i] in ['created_at', 'transaction_date', 'trade_date']:
                    # Parse datetime strings
                    processed_row.append(datetime.fromisoformat(val))
                else:
                    processed_row.append(val)
            data.append(processed_row)
    
    # Insert data using clickhouse_connect
    client.insert(table_name, data, column_names=headers)
    
    print(f"  Loaded {len(data)} rows")


def main():
    """Main entry point"""
    # Connect to ClickHouse
    print("Connecting to ClickHouse...")
    try:
        client = clickhouse_connect.get_client(
            host='localhost',
            port=8123,
            username='default',
            password='',
            database='data_quality'
        )
        print("Connected successfully")
    except ClickHouseError as e:
        print(f"Error connecting to ClickHouse: {e}")
        print("Make sure ClickHouse is running with: docker-compose up -d")
        sys.exit(1)
    
    # Create tables
    print("\nCreating tables...")
    for table_name, schema in TABLE_SCHEMAS.items():
        print(f"  Creating {table_name}...")
        client.command(schema)
    
    # Load CSV data
    print("\nLoading CSV data...")
    csv_dir = Path("fixtures/output")
    
    for table_name in TABLE_SCHEMAS.keys():
        csv_path = csv_dir / f"{table_name}.csv"
        load_csv_with_null_handling(client, table_name, csv_path)
    
    # Verify row counts
    print("\nVerifying row counts...")
    for table_name in TABLE_SCHEMAS.keys():
        result = client.query(f"SELECT count(*) FROM {table_name}")
        count = result.result_rows[0][0]
        print(f"  {table_name}: {count} rows")
    
    print("\nData loading complete!")


if __name__ == "__main__":
    main()
