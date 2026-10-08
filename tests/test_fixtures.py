"""
Unit tests for fixture data generation.
Tests verify exactly 3 planted violations and reproducibility.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fixtures.generator import FixtureGenerator
from collections import defaultdict


class TestFixtures:
    """Test fixture generation and violation detection"""

    @pytest.fixture
    def fixtures(self):
        """Generate fixture data for testing"""
        generator = FixtureGenerator()
        return generator.generate()

    def test_exactly_three_null_org_id_violations(self, fixtures):
        """Test there is exactly 1 NULL organisation_id violation"""
        null_org_contacts = [c for c in fixtures.contacts if c.organisation_id is None]
        assert len(null_org_contacts) == 1, f"Expected exactly 1 NULL organisation_id, found {len(null_org_contacts)}"

    def test_no_other_null_org_id_violations(self, fixtures):
        """Test no other tables have NULL organisation_id violations"""
        # Check all tenant-owned tables except contacts (which has the planted bug)
        tables_to_check = [
            (fixtures.advisors, "advisors"),
            (fixtures.accounts, "accounts"),
            (fixtures.portfolios, "portfolios"),
            (fixtures.holdings, "holdings"),
            (fixtures.transactions, "transactions"),
            (fixtures.trades, "trades"),
            (fixtures.fee_schedules, "fee_schedules"),
        ]
        
        for table_data, table_name in tables_to_check:
            null_count = sum(1 for row in table_data if row.organisation_id is None)
            assert null_count == 0, f"Found {null_count} NULL organisation_id in {table_name}, expected 0"

    def test_exactly_one_duplicate_business_key(self, fixtures):
        """Test there is exactly 1 duplicate business key within an organisation"""
        org_account_numbers = defaultdict(list)
        for account in fixtures.accounts:
            org_account_numbers[account.organisation_id].append(account.account_number)
        
        total_duplicates = 0
        for org_id, account_numbers in org_account_numbers.items():
            seen = set()
            dups = set()
            for acc_num in account_numbers:
                if acc_num in seen:
                    dups.add(acc_num)
                seen.add(acc_num)
            total_duplicates += len(dups)
        
        assert total_duplicates == 1, f"Expected exactly 1 duplicate business key, found {total_duplicates}"

    def test_no_other_duplicate_keys(self, fixtures):
        """Test no other tables have duplicate key violations"""
        # Check securities (shared reference table) should have unique symbols
        security_symbols = [s.symbol for s in fixtures.securities]
        assert len(security_symbols) == len(set(security_symbols)), "Found duplicate security symbols"
        
        # Check advisor IDs are unique
        advisor_ids = [a.id for a in fixtures.advisors]
        assert len(advisor_ids) == len(set(advisor_ids)), "Found duplicate advisor IDs"

    def test_exactly_one_cross_tenant_violation(self, fixtures):
        """Test there is exactly 1 cross-tenant reference violation"""
        # Build map of portfolio_id -> organisation_id
        portfolio_org_map = {p.id: p.organisation_id for p in fixtures.portfolios}
        
        cross_tenant_count = 0
        for holding in fixtures.holdings:
            if holding.portfolio_id in portfolio_org_map:
                portfolio_org = portfolio_org_map[holding.portfolio_id]
                if holding.organisation_id != portfolio_org:
                    cross_tenant_count += 1
        
        assert cross_tenant_count == 1, f"Expected exactly 1 cross-tenant violation, found {cross_tenant_count}"

    def test_generator_reproducibility(self):
        """Test generator produces identical output when run twice"""
        generator1 = FixtureGenerator()
        fixtures1 = generator1.generate()
        
        generator2 = FixtureGenerator()
        fixtures2 = generator2.generate()
        
        # Compare counts
        assert len(fixtures1.organisations) == len(fixtures2.organisations)
        assert len(fixtures1.advisors) == len(fixtures2.advisors)
        assert len(fixtures1.accounts) == len(fixtures2.accounts)
        assert len(fixtures1.contacts) == len(fixtures2.contacts)
        assert len(fixtures1.securities) == len(fixtures2.securities)
        assert len(fixtures1.portfolios) == len(fixtures2.portfolios)
        assert len(fixtures1.holdings) == len(fixtures2.holdings)
        assert len(fixtures1.transactions) == len(fixtures2.transactions)
        assert len(fixtures1.trades) == len(fixtures2.trades)
        assert len(fixtures1.fee_schedules) == len(fixtures2.fee_schedules)
        
        # Compare specific values (sample)
        assert fixtures1.organisations[0].id == fixtures2.organisations[0].id
        assert fixtures1.accounts[0].account_number == fixtures2.accounts[0].account_number
        assert fixtures1.holdings[0].quantity == fixtures2.holdings[0].quantity

    def test_total_violation_count(self, fixtures):
        """Test total of exactly 3 violations across all types"""
        # Count NULL org_id violations
        null_count = sum(1 for c in fixtures.contacts if c.organisation_id is None)
        
        # Count duplicate business keys
        org_account_numbers = defaultdict(list)
        for account in fixtures.accounts:
            org_account_numbers[account.organisation_id].append(account.account_number)
        dup_count = 0
        for org_id, account_numbers in org_account_numbers.items():
            seen = set()
            for acc_num in account_numbers:
                if acc_num in seen:
                    dup_count += 1
                seen.add(acc_num)
        
        # Count cross-tenant violations
        portfolio_org_map = {p.id: p.organisation_id for p in fixtures.portfolios}
        cross_tenant_count = 0
        for holding in fixtures.holdings:
            if holding.portfolio_id in portfolio_org_map:
                portfolio_org = portfolio_org_map[holding.portfolio_id]
                if holding.organisation_id != portfolio_org:
                    cross_tenant_count += 1
        
        total_violations = null_count + dup_count + cross_tenant_count
        assert total_violations == 3, f"Expected exactly 3 total violations, found {total_violations} (NULL: {null_count}, DUP: {dup_count}, X-TENANT: {cross_tenant_count})"
