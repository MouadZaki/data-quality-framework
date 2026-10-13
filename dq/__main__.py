"""
Runner module for executing data quality checks.
Loads configs, runs engine, and exits with appropriate code.
"""

import sys
import argparse
from dq.discovery import ConfigDiscovery
from dq.engine import QualityEngine
from dq.backends.fake import FakeBackend
from dq.backends.clickhouse import ClickHouseBackend
from fixtures.generator import FixtureGenerator


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Run data quality checks")
    parser.add_argument(
        "--backend",
        choices=["fake", "clickhouse"],
        default="fake",
        help="Backend to use: fake (in-memory) or clickhouse (database)"
    )
    args = parser.parse_args()

    # Load configs
    discovery = ConfigDiscovery()
    table_configs = discovery.discover()

    # Create backend based on choice
    if args.backend == "fake":
        # Load fixtures (suppress bug planting messages)
        generator = FixtureGenerator(verbose=False)
        fixtures = generator.generate()
        backend = FakeBackend(fixtures)
    elif args.backend == "clickhouse":
        backend = ClickHouseBackend(
            host='localhost',
            port=8123,
            username='default',
            password='',
            database='data_quality'
        )

    # Run engine
    engine = QualityEngine(backend)
    result = engine.run_checks(table_configs)

    # Print results
    engine.print_results(result)

    # Exit with non-zero code if any ERROR check failed
    if result.error_failures > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
