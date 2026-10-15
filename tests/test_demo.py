"""
Tests for the demo script (fake backend only, no Docker needed).
Each test asserts the expected outcome for each demo step.
"""

import copy
import sys
from io import StringIO

import pytest

from fixtures.generator import FixtureGenerator
from dq.backends.fake import FakeBackend
from dq.engine import QualityEngine
from dq.discovery import ConfigDiscovery
from dq.autogen import generate_checks


class TestDemoFakeBackend:
    """Test demo scenarios with fake backend"""

    @pytest.fixture
    def clean_fixtures(self):
        """Generate clean fixtures without bugs"""
        generator = FixtureGenerator(verbose=False, plant_bugs=False)
        return generator.generate()

    @pytest.fixture
    def table_configs(self):
        """Load table configurations"""
        discovery = ConfigDiscovery()
        return discovery.discover()

    def run_checks(self, backend, table_configs, autogen=True):
        """Run checks and return result"""
        if autogen:
            table_configs = generate_checks(table_configs, backend)
        
        engine = QualityEngine(backend)
        return engine.run_checks(table_configs)

    def test_step_0_clean_data(self, clean_fixtures, table_configs):
        """Step 0: Clean data - all checks pass"""
        backend = FakeBackend(clean_fixtures)
        result = self.run_checks(backend, table_configs)
        
        assert result.error_failures == 0
        assert result.warning_failures == 0
        assert result.total_checks > 0

    def test_step_1_duplicate_key(self, clean_fixtures, table_configs):
        """Step 1: Duplicate business key - only that check fails"""
        fixtures = copy.deepcopy(clean_fixtures)
        
        # Inject duplicate account_number
        org_accounts = [a for a in fixtures.accounts if a.organisation_id == "org_001"]
        if len(org_accounts) >= 2:
            org_accounts[1].account_number = org_accounts[0].account_number
        
        backend = FakeBackend(fixtures)
        result = self.run_checks(backend, table_configs)
        
        assert result.error_failures == 1
        assert result.warning_failures == 0

    def test_step_2_null_required_field(self, clean_fixtures, table_configs):
        """Step 2: NULL organisation_id - check fails"""
        fixtures = copy.deepcopy(clean_fixtures)
        
        # Inject NULL organisation_id in contacts (no foreign key references to contacts)
        # This avoids triggering auto-generated cross-tenant checks
        if fixtures.contacts:
            fixtures.contacts[0].organisation_id = None
        
        backend = FakeBackend(fixtures)
        result = self.run_checks(backend, table_configs)
        
        assert result.error_failures == 1
        assert result.warning_failures == 0

    def test_step_3_cross_tenant_leak(self, clean_fixtures, table_configs):
        """Step 3: Cross-tenant leak - check fails"""
        fixtures = copy.deepcopy(clean_fixtures)
        
        # Inject cross-tenant leak
        org1_holdings = [h for h in fixtures.holdings if h.organisation_id == "org_001"]
        org2_portfolios = [p for p in fixtures.portfolios if p.organisation_id == "org_002"]
        if org1_holdings and org2_portfolios:
            org1_holdings[0].portfolio_id = org2_portfolios[0].id
        
        backend = FakeBackend(fixtures)
        result = self.run_checks(backend, table_configs)
        
        assert result.error_failures == 1
        assert result.warning_failures == 0

    def test_step_4_auto_generated_checks(self, clean_fixtures, table_configs):
        """Step 4: Auto-generated checks catch leak, missed without auto-gen"""
        fixtures = copy.deepcopy(clean_fixtures)
        
        # Inject cross-tenant leak in trades
        org1_trades = [t for t in fixtures.trades if t.organisation_id == "org_001"]
        org2_accounts = [a for a in fixtures.accounts if a.organisation_id == "org_002"]
        if org1_trades and org2_accounts:
            org1_trades[0].account_id = org2_accounts[0].id
        
        backend = FakeBackend(fixtures)
        
        # With auto-generation ON
        result_auto = self.run_checks(backend, table_configs, autogen=True)
        assert result_auto.error_failures == 1
        
        # With auto-generation OFF
        result_no_auto = self.run_checks(backend, table_configs, autogen=False)
        assert result_no_auto.error_failures == 0

    def test_step_5_warning_only(self, clean_fixtures, table_configs):
        """Step 5: WARNING-only problem - warning logged, no error"""
        fixtures = copy.deepcopy(clean_fixtures)
        
        # Inject out-of-range fee rate
        if fixtures.fee_schedules:
            fixtures.fee_schedules[0].rate = 0.15  # 15%, outside 0-0.1 range
        
        backend = FakeBackend(fixtures)
        result = self.run_checks(backend, table_configs)
        
        assert result.error_failures == 0
        assert result.warning_failures == 1
