"""
Verification script to confirm all 3 planted bugs are present in the fixture data.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fixtures.generator import FixtureGenerator


def verify_bugs():
    """Verify all 3 bugs are present in the generated fixtures"""
    print("Verifying planted bugs...\n")
    
    generator = FixtureGenerator()
    fixtures = generator.generate()
    
    # Verify Bug #1: NULL organisation_id in contacts
    null_org_contacts = [c for c in fixtures.contacts if c.organisation_id is None]
    if null_org_contacts:
        print(f"✓ Bug #1 VERIFIED: Found {len(null_org_contacts)} contact(s) with NULL organisation_id")
        for contact in null_org_contacts:
            print(f"  - Contact ID: {contact.id}")
    else:
        print("✗ Bug #1 NOT FOUND: No contacts with NULL organisation_id")
    
    # Verify Bug #2: Duplicate account_number within same organisation
    from collections import defaultdict
    org_account_numbers = defaultdict(list)
    for account in fixtures.accounts:
        org_account_numbers[account.organisation_id].append(account.account_number)
    
    duplicates_found = False
    for org_id, account_numbers in org_account_numbers.items():
        seen = set()
        dups = set()
        for acc_num in account_numbers:
            if acc_num in seen:
                dups.add(acc_num)
            seen.add(acc_num)
        if dups:
            duplicates_found = True
            print(f"✓ Bug #2 VERIFIED: Found duplicate account_number(s) in org {org_id}: {dups}")
    
    if not duplicates_found:
        print("✗ Bug #2 NOT FOUND: No duplicate account_numbers within organisations")
    
    # Verify Bug #3: Cross-tenant leak (holding references portfolio from different org)
    # Build a map of portfolio_id -> organisation_id
    portfolio_org_map = {p.id: p.organisation_id for p in fixtures.portfolios}
    
    cross_tenant_leaks = []
    for holding in fixtures.holdings:
        if holding.portfolio_id in portfolio_org_map:
            portfolio_org = portfolio_org_map[holding.portfolio_id]
            if holding.organisation_id != portfolio_org:
                cross_tenant_leaks.append((holding, portfolio_org))
    
    if cross_tenant_leaks:
        print(f"✓ Bug #3 VERIFIED: Found {len(cross_tenant_leaks)} holding(s) with cross-tenant reference")
        for holding, portfolio_org in cross_tenant_leaks:
            print(f"  - Holding {holding.id} (org {holding.organisation_id}) references portfolio {holding.portfolio_id} (org {portfolio_org})")
    else:
        print("✗ Bug #3 NOT FOUND: No cross-tenant leaks detected")
    
    print("\n" + "="*50)
    print("Verification complete.")
    print("="*50)


if __name__ == "__main__":
    verify_bugs()
