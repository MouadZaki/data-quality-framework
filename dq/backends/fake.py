"""
Fake in-memory database backend for unit testing.
Uses fixture data without requiring a database connection.
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dq.engine import DatabaseBackend


class FakeBackend(DatabaseBackend):
    """In-memory backend using fixture data for unit testing"""

    def __init__(self, fixtures):
        """
        Initialize with fixture data
        
        Args:
            fixtures: Fixtures object from fixtures.generator
        """
        self.data = self._convert_fixtures_to_dict(fixtures)

    def _convert_fixtures_to_dict(self, fixtures) -> Dict[str, List[Dict]]:
        """Convert fixture dataclasses to dictionary format for querying"""
        data = {
            "organisations": [],
            "advisors": [],
            "accounts": [],
            "contacts": [],
            "securities": [],
            "portfolios": [],
            "holdings": [],
            "transactions": [],
            "trades": [],
            "fee_schedules": []
        }
        
        for org in fixtures.organisations:
            data["organisations"].append({
                "id": org.id,
                "name": org.name,
                "created_at": org.created_at
            })
        
        for advisor in fixtures.advisors:
            data["advisors"].append({
                "id": advisor.id,
                "organisation_id": advisor.organisation_id,
                "name": advisor.name,
                "email": advisor.email
            })
        
        for account in fixtures.accounts:
            data["accounts"].append({
                "id": account.id,
                "organisation_id": account.organisation_id,
                "advisor_id": account.advisor_id,
                "account_number": account.account_number,
                "account_type": account.account_type,
                "balance": account.balance
            })
        
        for contact in fixtures.contacts:
            data["contacts"].append({
                "id": contact.id,
                "organisation_id": contact.organisation_id,
                "account_id": contact.account_id,
                "name": contact.name,
                "email": contact.email,
                "phone": contact.phone
            })
        
        for security in fixtures.securities:
            data["securities"].append({
                "id": security.id,
                "symbol": security.symbol,
                "name": security.name,
                "asset_class": security.asset_class
            })
        
        for portfolio in fixtures.portfolios:
            data["portfolios"].append({
                "id": portfolio.id,
                "organisation_id": portfolio.organisation_id,
                "account_id": portfolio.account_id,
                "name": portfolio.name
            })
        
        for holding in fixtures.holdings:
            data["holdings"].append({
                "id": holding.id,
                "organisation_id": holding.organisation_id,
                "portfolio_id": holding.portfolio_id,
                "security_id": holding.security_id,
                "quantity": holding.quantity,
                "avg_cost": holding.avg_cost
            })
        
        for transaction in fixtures.transactions:
            data["transactions"].append({
                "id": transaction.id,
                "organisation_id": transaction.organisation_id,
                "account_id": transaction.account_id,
                "transaction_type": transaction.transaction_type,
                "amount": transaction.amount,
                "transaction_date": transaction.transaction_date
            })
        
        for trade in fixtures.trades:
            data["trades"].append({
                "id": trade.id,
                "organisation_id": trade.organisation_id,
                "account_id": trade.account_id,
                "security_id": trade.security_id,
                "quantity": trade.quantity,
                "price": trade.price,
                "trade_date": trade.trade_date
            })
        
        for fee_schedule in fixtures.fee_schedules:
            data["fee_schedules"].append({
                "id": fee_schedule.id,
                "organisation_id": fee_schedule.organisation_id,
                "fee_type": fee_schedule.fee_type,
                "rate": fee_schedule.rate,
                "min_fee": fee_schedule.min_fee
            })
        
        return data

    def get_row_count(self, table_name: str) -> int:
        """Get total row count for a table"""
        return len(self.data.get(table_name, []))

    def count_null_values(self, table_name: str, column: str) -> int:
        """Count NULL values in a column"""
        table_data = self.data.get(table_name, [])
        null_count = 0
        for row in table_data:
            if row.get(column) is None:
                null_count += 1
        return null_count

    def count_duplicate_keys(
        self,
        table_name: str,
        columns: List[str],
        group_by: Optional[List[str]] = None
    ) -> int:
        """Count duplicate key violations"""
        table_data = self.data.get(table_name, [])
        
        if group_by:
            # Count duplicates within each group
            group_keys = defaultdict(list)
            for row in table_data:
                group_key = tuple(row.get(col) for col in group_by)
                key_value = tuple(row.get(col) for col in columns)
                group_keys[group_key].append(key_value)
            
            duplicate_count = 0
            for group_key, key_values in group_keys.items():
                seen = set()
                for key_value in key_values:
                    if key_value in seen:
                        duplicate_count += 1
                    seen.add(key_value)
            return duplicate_count
        else:
            # Count duplicates globally
            key_counts = defaultdict(int)
            for row in table_data:
                key_value = tuple(row.get(col) for col in columns)
                key_counts[key_value] += 1
            
            duplicate_count = sum(count - 1 for count in key_counts.values() if count > 1)
            return duplicate_count

    def count_cross_tenant_violations(
        self,
        table_name: str,
        column: str,
        referenced_table: str,
        referenced_column: str,
        tenant_column: str
    ) -> int:
        """Count cross-tenant reference violations"""
        table_data = self.data.get(table_name, [])
        ref_data = self.data.get(referenced_table, [])
        
        # Build map: referenced_column -> tenant_column
        ref_tenant_map = {}
        for row in ref_data:
            ref_key = row.get(referenced_column)
            ref_tenant = row.get(tenant_column)
            if ref_key is not None:
                ref_tenant_map[ref_key] = ref_tenant
        
        violation_count = 0
        for row in table_data:
            ref_key = row.get(column)
            row_tenant = row.get(tenant_column)
            
            if ref_key is not None and row_tenant is not None:
                if ref_key in ref_tenant_map:
                    ref_tenant = ref_tenant_map[ref_key]
                    if ref_tenant != row_tenant:
                        violation_count += 1
        
        return violation_count

    def count_range_violations(
        self,
        table_name: str,
        column: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None
    ) -> int:
        """Count values outside specified range"""
        table_data = self.data.get(table_name, [])
        violation_count = 0
        
        for row in table_data:
            value = row.get(column)
            if value is None:
                continue
            
            if min_value is not None and value < min_value:
                violation_count += 1
            if max_value is not None and value > max_value:
                violation_count += 1
        
        return violation_count
