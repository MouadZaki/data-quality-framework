"""
Test that the framework follows the counts-only rule.
No fixture row IDs or values should appear in engine output.
"""

import sys
from io import StringIO

from fixtures.generator import FixtureGenerator
from dq.backends.fake import FakeBackend
from dq.engine import QualityEngine
from dq.discovery import ConfigDiscovery
from dq.autogen import generate_checks


def test_demo_output_counts_only():
    """Test that demo output contains no fixture row IDs or values"""
    # Generate fixtures with bugs (as in demo)
    generator = FixtureGenerator(verbose=False, plant_bugs=True)
    fixtures = generator.generate()
    
    # Create backend and run checks
    backend = FakeBackend(fixtures)
    discovery = ConfigDiscovery()
    table_configs = discovery.discover()
    table_configs = generate_checks(table_configs, backend)
    
    engine = QualityEngine(backend)
    result = engine.run_checks(table_configs)
    
    # Capture output
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    engine.print_results(result)
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout
    
    # Fixture IDs and values that should NOT appear in output
    # Note: Check names may contain table prefixes (e.g., 'fee_rate_range'), so we exclude those
    forbidden_patterns = [
        # Row IDs (full patterns, not just prefixes)
        "cnt_acc_org_001_1",
        "acc_org_001_0001",
        "adv_org_001_1",
        "prt_acc_org_001_1",
        "hld_prt_acc_org_001_1",
        "txn_acc_org_001_1",
        "trd_acc_org_001_1",
        # Account numbers (full patterns)
        "ORG_001-0001",
        "ORG_002-0001",
        "ORG_003-0001",
        # Emails (specific patterns)
        "advisor1@org_001.com",
        "advisor2@org_001.com",
        "client@acc_org_001_1.com",
        # Names
        "WealthCorp",
        "AssetMgmt LLC",
        "PrimeInvest",
        "Apple Inc",
        "Microsoft Corp",
        "Alphabet Inc",
        # Security symbols
        "AAPL",
        "MSFT",
        "GOOGL",
        "VTI",
        "BND",
        "GLD",
    ]
    
    # Check that none of the forbidden patterns appear
    for pattern in forbidden_patterns:
        assert pattern not in output, f"Counts-only rule violated: '{pattern}' found in output"
    
    # Output should only contain counts and check names
    assert "violations" in output or "PASS" in output, "Output should contain check results"
    assert "Total checks" in output, "Output should contain summary"
