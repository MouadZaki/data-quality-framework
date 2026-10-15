"""
Demo script for data quality framework.
Shows how the engine catches various data quality issues.
"""

import sys
import argparse
import copy
from io import StringIO

from fixtures.generator import FixtureGenerator
from dq.backends.fake import FakeBackend
from dq.backends.clickhouse import ClickHouseBackend
from dq.engine import QualityEngine
from dq.discovery import ConfigDiscovery
from dq.autogen import generate_checks


class DemoRunner:
    """Runs demo scenarios"""

    def __init__(self, backend: str = "fake", pause: bool = False):
        self.backend_type = backend
        self.pause = pause
        self.mismatch_count = 0

    def print_heading(self, step: int, title: str) -> None:
        """Print a step heading"""
        print(f"\n{'='*70}")
        print(f"STEP {step}: {title}")
        print('='*70)

    def wait_for_enter(self) -> None:
        """Wait for user to press Enter if pause is enabled"""
        if self.pause:
            input("\nPress Enter to continue...")

    def run_checks_and_capture(self, backend, table_configs, autogen: bool = True) -> tuple:
        """Run checks and capture output"""
        if autogen:
            table_configs = generate_checks(table_configs, backend)
        
        engine = QualityEngine(backend)
        result = engine.run_checks(table_configs)
        
        # Capture output
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        engine.print_results(result)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        
        return result, output

    def check_result(self, step: int, result, expected_errors: int, expected_warnings: int, 
                     expected_exit_code: int, description: str) -> None:
        """Check if result matches expectations"""
        errors_match = result.error_failures == expected_errors
        warnings_match = result.warning_failures == expected_warnings
        exit_code_match = (1 if result.error_failures > 0 else 0) == expected_exit_code
        
        if errors_match and warnings_match and exit_code_match:
            print(f"\n✓ OK: {description}")
        else:
            print(f"\n✗ MISMATCH: {description}")
            print(f"  Expected: {expected_errors} errors, {expected_warnings} warnings, exit code {expected_exit_code}")
            print(f"  Got: {result.error_failures} errors, {result.warning_failures} warnings, exit code {1 if result.error_failures > 0 else 0}")
            self.mismatch_count += 1

    def step_0_clean_data(self) -> None:
        """Step 0: Clean data - all checks pass"""
        self.print_heading(0, "Clean Data")
        print("Generating clean fixtures (no planted bugs)...")
        generator = FixtureGenerator(verbose=False, plant_bugs=False)
        fixtures = generator.generate()
        
        backend = FakeBackend(fixtures)
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(0, result, 0, 0, 0, "All checks pass, CONTINUE, exit code 0")
        self.wait_for_enter()

    def step_1_duplicate_key(self) -> None:
        """Step 1: Duplicate business key"""
        self.print_heading(1, "Duplicate Business Key")
        print("Injecting: duplicate account_number in one organisation")
        
        generator = FixtureGenerator(verbose=False, plant_bugs=False)
        fixtures = generator.generate()
        
        # Inject duplicate account_number
        org_accounts = [a for a in fixtures.accounts if a.organisation_id == "org_001"]
        if len(org_accounts) >= 2:
            org_accounts[1].account_number = org_accounts[0].account_number
            print("  Duplicated account_number in org_001")
        
        backend = FakeBackend(fixtures)
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(1, result, 1, 0, 1, "Only account_number_unique check fails, HALT, exit code 1")
        self.wait_for_enter()

    def step_2_null_required_field(self) -> None:
        """Step 2: Missing required field (NULL organisation_id)"""
        self.print_heading(2, "Missing Required Field")
        print("Injecting: NULL organisation_id in contacts table")
        
        generator = FixtureGenerator(verbose=False, plant_bugs=False)
        fixtures = generator.generate()
        
        # Inject NULL organisation_id in contacts (no foreign key references to contacts)
        # This avoids triggering auto-generated cross-tenant checks
        if fixtures.contacts:
            fixtures.contacts[0].organisation_id = None
            print("  Set organisation_id to NULL for one contact row")
        
        backend = FakeBackend(fixtures)
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(2, result, 1, 0, 1, "NULL org_id check fails, HALT, exit code 1")
        self.wait_for_enter()

    def step_3_cross_tenant_leak(self) -> None:
        """Step 3: Cross-tenant leak"""
        self.print_heading(3, "Cross-Tenant Leak")
        print("Injecting: holding pointing to another organisation's portfolio")
        
        generator = FixtureGenerator(verbose=False, plant_bugs=False)
        fixtures = generator.generate()
        
        # Inject cross-tenant leak
        org1_holdings = [h for h in fixtures.holdings if h.organisation_id == "org_001"]
        org2_portfolios = [p for p in fixtures.portfolios if p.organisation_id == "org_002"]
        if org1_holdings and org2_portfolios:
            org1_holdings[0].portfolio_id = org2_portfolios[0].id
            print("  One holding in org_001 now references a portfolio from org_002")
        
        backend = FakeBackend(fixtures)
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(3, result, 1, 0, 1, "Cross-tenant check fails, HALT, exit code 1")
        self.wait_for_enter()

    def step_4_auto_generated_checks(self) -> None:
        """Step 4: Auto-generated checks"""
        self.print_heading(4, "Auto-Generated Checks")
        print("Injecting: trade whose account_id belongs to another organisation")
        print("(trades table has no hand-written cross-tenant check)")
        
        generator = FixtureGenerator(verbose=False, plant_bugs=False)
        fixtures = generator.generate()
        
        # Inject cross-tenant leak in trades
        org1_trades = [t for t in fixtures.trades if t.organisation_id == "org_001"]
        org2_accounts = [a for a in fixtures.accounts if a.organisation_id == "org_002"]
        if org1_trades and org2_accounts:
            org1_trades[0].account_id = org2_accounts[0].id
            print("  One trade in org_001 now references an account from org_002")
        
        backend = FakeBackend(fixtures)
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        # Run with auto-generation ON
        print("\n--- Running with auto-generation ON ---")
        result_auto, output_auto = self.run_checks_and_capture(backend, table_configs, autogen=True)
        print(output_auto)
        
        # Run with auto-generation OFF
        print("\n--- Running with auto-generation OFF (--no-autogen) ---")
        result_no_auto, output_no_auto = self.run_checks_and_capture(backend, table_configs, autogen=False)
        print(output_no_auto)
        
        # Check results
        auto_catch = result_auto.error_failures == 1
        no_auto_miss = result_no_auto.error_failures == 0
        
        if auto_catch and no_auto_miss:
            print(f"\n✓ OK: Auto-generation catches the leak, --no-autogen misses it")
        else:
            print(f"\n✗ MISMATCH: Auto-generation behavior incorrect")
            print(f"  With auto-gen: {result_auto.error_failures} errors (expected 1)")
            print(f"  Without auto-gen: {result_no_auto.error_failures} errors (expected 0)")
            self.mismatch_count += 1
        
        self.wait_for_enter()

    def step_5_warning_only(self) -> None:
        """Step 5: WARNING-only problem"""
        self.print_heading(5, "WARNING-Only Problem")
        print("Injecting: fee rate outside allowed range")
        
        generator = FixtureGenerator(verbose=False, plant_bugs=False)
        fixtures = generator.generate()
        
        # Inject out-of-range fee rate
        if fixtures.fee_schedules:
            fixtures.fee_schedules[0].rate = 0.15  # 15%, outside 0-0.1 range
            print("  Set fee rate to 15% (outside 0-10% range) for one fee schedule")
        
        backend = FakeBackend(fixtures)
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(5, result, 0, 1, 0, "WARNING logged, run continues, exit code 0")
        self.wait_for_enter()

    def run_fake_backend_demo(self) -> None:
        """Run the fake backend demo"""
        print("\n" + "="*70)
        print("DATA QUALITY FRAMEWORK DEMO - FAKE BACKEND")
        print("="*70)
        print("\nThis demo shows how the engine catches various data quality issues.")
        print("Each step starts from clean data, injects one corruption,")
        print("and runs the quality checks.")
        
        self.step_0_clean_data()
        self.step_1_duplicate_key()
        self.step_2_null_required_field()
        self.step_3_cross_tenant_leak()
        self.step_4_auto_generated_checks()
        self.step_5_warning_only()
        
        print(f"\n{'='*70}")
        print("DEMO COMPLETE")
        print('='*70)
        
        if self.mismatch_count == 0:
            print("✓ All steps matched expected outcomes")
        else:
            print(f"✗ {self.mismatch_count} step(s) did not match expected outcomes")
        
        return 0 if self.mismatch_count == 0 else 1

    def run_clickhouse_demo(self) -> int:
        """Run the ClickHouse backend demo"""
        print("\n" + "="*70)
        print("DATA QUALITY FRAMEWORK DEMO - CLICKHOUSE BACKEND")
        print("="*70)
        print("\nThis demo runs against a real ClickHouse database.")
        print("Using separate database 'dq_demo' to avoid affecting main tables.")
        
        try:
            import clickhouse_connect
            from clickhouse_connect.driver.exceptions import Error as ClickHouseError
            
            # Connect to ClickHouse (default database first to create dq_demo)
            client = clickhouse_connect.get_client(
                host='localhost',
                port=8123,
                username='default',
                password='',
                database='default'
            )
            
            # Create dq_demo database
            try:
                client.command("DROP DATABASE IF EXISTS dq_demo")
                client.command("CREATE DATABASE dq_demo")
                print("\n✓ Created database 'dq_demo'")
            except ClickHouseError as e:
                print(f"\n✗ Failed to create database: {e}")
                return 1
            
            # Load clean data into dq_demo
            print("\nLoading clean data into dq_demo...")
            self._load_clean_data_clickhouse(client)
            
            # Create backend for dq_demo
            backend = ClickHouseBackend(
                host='localhost',
                port=8123,
                username='default',
                password='',
                database='dq_demo'
            )
            
            discovery = ConfigDiscovery()
            table_configs = discovery.discover()
            
            # Run steps
            self.step_0_clean_data_ch(backend, table_configs, client)
            self.step_1_duplicate_key_ch(backend, table_configs, client)
            self.step_2_null_required_field_ch(backend, table_configs, client)
            self.step_3_cross_tenant_leak_ch(backend, table_configs, client)
            self.step_4_auto_generated_checks_ch(backend, table_configs, client)
            self.step_5_warning_only_ch(backend, table_configs, client)
            
            print(f"\n{'='*70}")
            print("DEMO COMPLETE")
            print('='*70)
            
            if self.mismatch_count == 0:
                print("✓ All steps matched expected outcomes")
            else:
                print(f"✗ {self.mismatch_count} step(s) did not match expected outcomes")
            
            # Cleanup
            try:
                client.command("DROP DATABASE dq_demo")
                print("\n✓ Cleaned up dq_demo database")
            except:
                pass
            
            return 0 if self.mismatch_count == 0 else 1
            
        except ClickHouseError as e:
            print(f"\n✗ Cannot connect to ClickHouse: {e}")
            print("Start ClickHouse with: docker-compose up -d")
            return 1

    def _load_clean_data_clickhouse(self, client) -> None:
        """Load clean fixture data into ClickHouse"""
        generator = FixtureGenerator(verbose=False, plant_bugs=False)
        fixtures = generator.generate()
        
        # Create tables and load data
        tables = [
            ("organisations", fixtures.organisations),
            ("advisors", fixtures.advisors),
            ("accounts", fixtures.accounts),
            ("contacts", fixtures.contacts),
            ("securities", fixtures.securities),
            ("portfolios", fixtures.portfolios),
            ("holdings", fixtures.holdings),
            ("transactions", fixtures.transactions),
            ("trades", fixtures.trades),
            ("fee_schedules", fixtures.fee_schedules),
        ]
        
        for table_name, data in tables:
            if not data:
                continue
            
            # Get column names from first row
            import dataclasses
            columns = list(data[0].__dataclass_fields__.keys())
            
            # Create table
            col_defs = []
            for col in columns:
                if col == 'created_at' or col == 'transaction_date' or col == 'trade_date':
                    col_defs.append(f"{col} DateTime")
                elif col == 'balance' or col == 'quantity' or col == 'avg_cost' or col == 'amount' or col == 'price' or col == 'rate' or col == 'min_fee':
                    col_defs.append(f"{col} Float64")
                elif col == 'organisation_id' or col == 'advisor_id' or col == 'account_id' or col == 'portfolio_id' or col == 'security_id':
                    # These can be NULL in some scenarios
                    col_defs.append(f"{col} Nullable(String)")
                else:
                    col_defs.append(f"{col} String")
            
            create_sql = f"CREATE TABLE dq_demo.{table_name} ({', '.join(col_defs)}) ENGINE = MergeTree() ORDER BY id"
            client.command(create_sql)
            
            # Insert data
            import dataclasses
            from datetime import datetime
            for row in data:
                row_dict = dataclasses.asdict(row)
                values = []
                for col in columns:
                    val = row_dict[col]
                    if val is None:
                        values.append("NULL")
                    elif isinstance(val, str):
                        values.append(f"'{val}'")
                    elif isinstance(val, datetime):
                        # Format datetime for ClickHouse: '2020-01-01 00:00:00'
                        values.append(f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'")
                    else:
                        values.append(str(val))
                
                insert_sql = f"INSERT INTO dq_demo.{table_name} VALUES ({', '.join(values)})"
                client.command(insert_sql)
            
            print(f"  Loaded {len(data)} rows into {table_name}")
        
        print("✓ Clean data loaded")

    def step_0_clean_data_ch(self, backend, table_configs, client) -> None:
        """Step 0: Clean data - all checks pass (ClickHouse)"""
        self.print_heading(0, "Clean Data")
        print("Running checks on clean data...")
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(0, result, 0, 0, 0, "All checks pass, CONTINUE, exit code 0")
        self.wait_for_enter()

    def step_1_duplicate_key_ch(self, backend, table_configs, client) -> None:
        """Step 1: Duplicate business key (ClickHouse)"""
        self.print_heading(1, "Duplicate Business Key")
        print("Injecting: duplicate account_number in one organisation")
        
        # Get first account_number and second account ID in org_001
        result = client.query("SELECT account_number, id FROM dq_demo.accounts WHERE organisation_id = 'org_001' LIMIT 2")
        if len(result.result_rows) >= 2:
            acc_num = result.result_rows[0][0]
            second_id = result.result_rows[1][1]
            # Update second account to have same account_number
            client.command(f"ALTER TABLE dq_demo.accounts UPDATE account_number = '{acc_num}' WHERE id = '{second_id}'")
            print("  Duplicated account_number in org_001")
            self._wait_for_mutations(client)
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(1, result, 1, 0, 1, "Only account_number_unique check fails, HALT, exit code 1")
        
        # Reset to clean data
        self._reset_to_clean_ch(client)
        self.wait_for_enter()

    def step_2_null_required_field_ch(self, backend, table_configs, client) -> None:
        """Step 2: Missing required field (ClickHouse)"""
        self.print_heading(2, "Missing Required Field")
        print("Injecting: NULL organisation_id in contacts table")
        
        # Get first contact ID
        result = client.query("SELECT id FROM dq_demo.contacts LIMIT 1")
        if result.result_rows:
            contact_id = result.result_rows[0][0]
            # Set organisation_id to NULL
            client.command(f"ALTER TABLE dq_demo.contacts UPDATE organisation_id = NULL WHERE id = '{contact_id}'")
            print("  Set organisation_id to NULL for one contact row")
            self._wait_for_mutations(client)
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(2, result, 1, 0, 1, "NULL org_id check fails, HALT, exit code 1")
        
        # Reset to clean data
        self._reset_to_clean_ch(client)
        self.wait_for_enter()

    def step_3_cross_tenant_leak_ch(self, backend, table_configs, client) -> None:
        """Step 3: Cross-tenant leak (ClickHouse)"""
        self.print_heading(3, "Cross-Tenant Leak")
        print("Injecting: holding pointing to another organisation's portfolio")
        
        # Get a holding in org_001 and a portfolio in org_002
        result = client.query("SELECT id FROM dq_demo.holdings WHERE organisation_id = 'org_001' LIMIT 1")
        if result.result_rows:
            holding_id = result.result_rows[0][0]
            result2 = client.query("SELECT id FROM dq_demo.portfolios WHERE organisation_id = 'org_002' LIMIT 1")
            if result2.result_rows:
                portfolio_id = result2.result_rows[0][0]
                client.command(f"ALTER TABLE dq_demo.holdings UPDATE portfolio_id = '{portfolio_id}' WHERE id = '{holding_id}'")
                print("  One holding in org_001 now references a portfolio from org_002")
                self._wait_for_mutations(client)
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(3, result, 1, 0, 1, "Cross-tenant check fails, HALT, exit code 1")
        
        # Reset to clean data
        self._reset_to_clean_ch(client)
        self.wait_for_enter()

    def step_4_auto_generated_checks_ch(self, backend, table_configs, client) -> None:
        """Step 4: Auto-generated checks (ClickHouse)"""
        self.print_heading(4, "Auto-Generated Checks")
        print("Injecting: trade whose account_id belongs to another organisation")
        print("(trades table has no hand-written cross-tenant check)")
        
        # Get a trade in org_001 and an account in org_002
        result = client.query("SELECT id FROM dq_demo.trades WHERE organisation_id = 'org_001' LIMIT 1")
        if result.result_rows:
            trade_id = result.result_rows[0][0]
            result2 = client.query("SELECT id FROM dq_demo.accounts WHERE organisation_id = 'org_002' LIMIT 1")
            if result2.result_rows:
                account_id = result2.result_rows[0][0]
                client.command(f"ALTER TABLE dq_demo.trades UPDATE account_id = '{account_id}' WHERE id = '{trade_id}'")
                print("  One trade in org_001 now references an account from org_002")
                self._wait_for_mutations(client)
        
        # Run with auto-generation ON
        print("\n--- Running with auto-generation ON ---")
        result_auto, output_auto = self.run_checks_and_capture(backend, table_configs, autogen=True)
        print(output_auto)
        
        # Run with auto-generation OFF
        print("\n--- Running with auto-generation OFF (--no-autogen) ---")
        result_no_auto, output_no_auto = self.run_checks_and_capture(backend, table_configs, autogen=False)
        print(output_no_auto)
        
        # Check results
        auto_catch = result_auto.error_failures == 1
        no_auto_miss = result_no_auto.error_failures == 0
        
        if auto_catch and no_auto_miss:
            print(f"\n✓ OK: Auto-generation catches the leak, --no-autogen misses it")
        else:
            print(f"\n✗ MISMATCH: Auto-generation behavior incorrect")
            print(f"  With auto-gen: {result_auto.error_failures} errors (expected 1)")
            print(f"  Without auto-gen: {result_no_auto.error_failures} errors (expected 0)")
            self.mismatch_count += 1
        
        # Reset to clean data
        self._reset_to_clean_ch(client)
        self.wait_for_enter()

    def step_5_warning_only_ch(self, backend, table_configs, client) -> None:
        """Step 5: WARNING-only problem (ClickHouse)"""
        self.print_heading(5, "WARNING-Only Problem")
        print("Injecting: fee rate outside allowed range")
        
        # Set first fee schedule rate to 15%
        client.command("ALTER TABLE dq_demo.fee_schedules UPDATE rate = 0.15 WHERE id = (SELECT id FROM dq_demo.fee_schedules LIMIT 1)")
        print("  Set fee rate to 15% (outside 0-10% range) for one fee schedule")
        self._wait_for_mutations(client)
        
        result, output = self.run_checks_and_capture(backend, table_configs)
        print(output)
        
        self.check_result(5, result, 0, 1, 0, "WARNING logged, run continues, exit code 0")
        
        # Reset to clean data
        self._reset_to_clean_ch(client)
        self.wait_for_enter()

    def _wait_for_mutations(self, client) -> None:
        """Wait for all ClickHouse mutations to complete"""
        import time
        max_wait = 30  # seconds
        waited = 0
        while waited < max_wait:
            result = client.query("SELECT count() FROM system.mutations WHERE database = 'dq_demo' AND is_done = 0")
            if result.result_rows[0][0] == 0:
                return
            time.sleep(0.5)
            waited += 0.5
        print("  Warning: Timed out waiting for mutations")

    def _reset_to_clean_ch(self, client) -> None:
        """Reset ClickHouse data to clean state"""
        # Drop and recreate database
        client.command("DROP DATABASE dq_demo")
        client.command("CREATE DATABASE dq_demo")
        self._load_clean_data_clickhouse(client)
        print("✓ Reset to clean data")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Run data quality framework demo")
    parser.add_argument(
        "--backend",
        choices=["fake", "clickhouse"],
        default="fake",
        help="Backend to use: fake (in-memory) or clickhouse (database)"
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help="Pause between steps (for video recording)"
    )
    
    args = parser.parse_args()
    
    runner = DemoRunner(backend=args.backend, pause=args.pause)
    
    if args.backend == "fake":
        exit_code = runner.run_fake_backend_demo()
    else:
        exit_code = runner.run_clickhouse_demo()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
