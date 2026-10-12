"""
Runner module for executing data quality checks.
Loads configs, runs engine, and exits with appropriate code.
"""

import sys
from dq.discovery import ConfigDiscovery
from dq.engine import QualityEngine
from dq.backends.fake import FakeBackend
from fixtures.generator import FixtureGenerator


def main():
    """Main entry point"""
    # Load fixtures (suppress bug planting messages)
    generator = FixtureGenerator(verbose=False)
    fixtures = generator.generate()
    
    # Create fake backend with fixtures
    backend = FakeBackend(fixtures)
    
    # Load configs
    discovery = ConfigDiscovery()
    table_configs = discovery.discover()
    
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
