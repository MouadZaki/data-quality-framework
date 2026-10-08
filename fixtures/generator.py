"""
Fixture data generator for wealth management domain.
Generates 10 normalized tables with 3 fake organisations and 3 planted bugs.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime, timedelta


@dataclass
class Organisation:
    """Organisation entity"""
    id: str
    name: str
    created_at: datetime


@dataclass
class Advisor:
    """Advisor entity"""
    id: str
    organisation_id: str
    name: str
    email: str


@dataclass
class Account:
    """Account entity"""
    id: str
    organisation_id: str
    advisor_id: str
    account_number: str  # Business key
    account_type: str
    balance: float


@dataclass
class Contact:
    """Contact entity"""
    id: str
    organisation_id: str
    account_id: str
    name: str
    email: str
    phone: str


@dataclass
class Security:
    """Security entity - SHARED reference table (no organisation_id)"""
    id: str
    symbol: str
    name: str
    asset_class: str


@dataclass
class Portfolio:
    """Portfolio entity"""
    id: str
    organisation_id: str
    account_id: str
    name: str


@dataclass
class Holding:
    """Holding entity"""
    id: str
    organisation_id: str
    portfolio_id: str
    security_id: str
    quantity: float
    avg_cost: float


@dataclass
class Transaction:
    """Transaction entity"""
    id: str
    organisation_id: str
    account_id: str
    transaction_type: str
    amount: float
    transaction_date: datetime


@dataclass
class Trade:
    """Trade entity"""
    id: str
    organisation_id: str
    account_id: str
    security_id: str
    quantity: float
    price: float
    trade_date: datetime


@dataclass
class FeeSchedule:
    """Fee schedule entity"""
    id: str
    organisation_id: str
    fee_type: str
    rate: float
    min_fee: float


@dataclass
class Fixtures:
    """Container for all fixture data"""
    organisations: List[Organisation] = field(default_factory=list)
    advisors: List[Advisor] = field(default_factory=list)
    accounts: List[Account] = field(default_factory=list)
    contacts: List[Contact] = field(default_factory=list)
    securities: List[Security] = field(default_factory=list)
    portfolios: List[Portfolio] = field(default_factory=list)
    holdings: List[Holding] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)
    fee_schedules: List[FeeSchedule] = field(default_factory=list)

    def print_counts(self) -> None:
        """Print row counts for each table"""
        print("\n=== Fixture Row Counts ===")
        print(f"organisations: {len(self.organisations)}")
        print(f"advisors: {len(self.advisors)}")
        print(f"accounts: {len(self.accounts)}")
        print(f"contacts: {len(self.contacts)}")
        print(f"securities: {len(self.securities)} (shared reference table)")
        print(f"portfolios: {len(self.portfolios)}")
        print(f"holdings: {len(self.holdings)}")
        print(f"transactions: {len(self.transactions)}")
        print(f"trades: {len(self.trades)}")
        print(f"fee_schedules: {len(self.fee_schedules)}")
        print("========================\n")


class FixtureGenerator:
    """Generates fixture data with planted bugs"""

    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.fixtures = Fixtures()
        self.org_ids: List[str] = []

    def generate(self) -> Fixtures:
        """Generate all fixture data"""
        self._generate_organisations()
        self._generate_securities()
        self._generate_advisors()
        self._generate_accounts()
        self._generate_contacts()
        self._generate_portfolios()
        self._generate_holdings()
        self._generate_transactions()
        self._generate_trades()
        self._generate_fee_schedules()
        self._plant_bugs()
        return self.fixtures

    def _generate_organisations(self) -> None:
        """Generate 3 fake organisations"""
        org_names = ["WealthCorp", "AssetMgmt LLC", "PrimeInvest"]
        for i, name in enumerate(org_names):
            org = Organisation(
                id=f"org_{i+1:03d}",
                name=name,
                created_at=datetime(2020, 1, 1) + timedelta(days=i*30)
            )
            self.fixtures.organisations.append(org)
            self.org_ids.append(org.id)

    def _generate_securities(self) -> None:
        """Generate shared securities (no organisation_id)"""
        securities_data = [
            ("AAPL", "Apple Inc", "Equity"),
            ("MSFT", "Microsoft Corp", "Equity"),
            ("GOOGL", "Alphabet Inc", "Equity"),
            ("VTI", "Vanguard Total Stock", "ETF"),
            ("BND", "Vanguard Total Bond", "ETF"),
            ("GLD", "SPDR Gold Trust", "Commodity"),
        ]
        for i, (symbol, name, asset_class) in enumerate(securities_data):
            security = Security(
                id=f"sec_{i+1:03d}",
                symbol=symbol,
                name=name,
                asset_class=asset_class
            )
            self.fixtures.securities.append(security)

    def _generate_advisors(self) -> None:
        """Generate advisors for each organisation"""
        for org_id in self.org_ids:
            for i in range(2):
                advisor = Advisor(
                    id=f"adv_{org_id}_{i+1}",
                    organisation_id=org_id,
                    name=f"Advisor {i+1}",
                    email=f"advisor{i+1}@{org_id}.com"
                )
                self.fixtures.advisors.append(advisor)

    def _generate_accounts(self) -> None:
        """Generate accounts for each organisation"""
        account_types = ["Brokerage", "IRA", "401k"]
        for org_id in self.org_ids:
            org_advisors = [a for a in self.fixtures.advisors if a.organisation_id == org_id]
            for i in range(3):
                advisor = random.choice(org_advisors)
                account = Account(
                    id=f"acc_{org_id}_{i+1}",
                    organisation_id=org_id,
                    advisor_id=advisor.id,
                    account_number=f"{org_id.upper()}-{i+1:04d}",
                    account_type=random.choice(account_types),
                    balance=random.uniform(10000, 500000)
                )
                self.fixtures.accounts.append(account)

    def _generate_contacts(self) -> None:
        """Generate contacts for each account"""
        for org_id in self.org_ids:
            org_accounts = [a for a in self.fixtures.accounts if a.organisation_id == org_id]
            for account in org_accounts:
                contact = Contact(
                    id=f"cnt_{account.id}",
                    organisation_id=org_id,
                    account_id=account.id,
                    name=f"Client of {account.id}",
                    email=f"client@{account.id}.com",
                    phone=f"555-{random.randint(1000, 9999)}"
                )
                self.fixtures.contacts.append(contact)

    def _generate_portfolios(self) -> None:
        """Generate portfolios for each account"""
        for org_id in self.org_ids:
            org_accounts = [a for a in self.fixtures.accounts if a.organisation_id == org_id]
            for account in org_accounts:
                portfolio = Portfolio(
                    id=f"prt_{account.id}",
                    organisation_id=org_id,
                    account_id=account.id,
                    name=f"Portfolio for {account.account_number}"
                )
                self.fixtures.portfolios.append(portfolio)

    def _generate_holdings(self) -> None:
        """Generate holdings for each portfolio"""
        for org_id in self.org_ids:
            org_portfolios = [p for p in self.fixtures.portfolios if p.organisation_id == org_id]
            for portfolio in org_portfolios:
                for security in self.fixtures.securities[:3]:
                    holding = Holding(
                        id=f"hld_{portfolio.id}_{security.id}",
                        organisation_id=org_id,
                        portfolio_id=portfolio.id,
                        security_id=security.id,
                        quantity=random.uniform(10, 1000),
                        avg_cost=random.uniform(50, 200)
                    )
                    self.fixtures.holdings.append(holding)

    def _generate_transactions(self) -> None:
        """Generate transactions for each account"""
        transaction_types = ["Deposit", "Withdrawal", "Transfer"]
        for org_id in self.org_ids:
            org_accounts = [a for a in self.fixtures.accounts if a.organisation_id == org_id]
            for account in org_accounts:
                for i in range(2):
                    transaction = Transaction(
                        id=f"txn_{account.id}_{i+1}",
                        organisation_id=org_id,
                        account_id=account.id,
                        transaction_type=random.choice(transaction_types),
                        amount=random.uniform(1000, 50000),
                        transaction_date=datetime(2024, 1, 1) + timedelta(days=i*15)
                    )
                    self.fixtures.transactions.append(transaction)

    def _generate_trades(self) -> None:
        """Generate trades for each account"""
        for org_id in self.org_ids:
            org_accounts = [a for a in self.fixtures.accounts if a.organisation_id == org_id]
            for account in org_accounts:
                for i in range(2):
                    security = random.choice(self.fixtures.securities)
                    trade = Trade(
                        id=f"trd_{account.id}_{i+1}",
                        organisation_id=org_id,
                        account_id=account.id,
                        security_id=security.id,
                        quantity=random.uniform(10, 100),
                        price=random.uniform(50, 200),
                        trade_date=datetime(2024, 1, 1) + timedelta(days=i*7)
                    )
                    self.fixtures.trades.append(trade)

    def _generate_fee_schedules(self) -> None:
        """Generate fee schedules for each organisation"""
        fee_types = ["Management", "Trading", "Advisory"]
        for org_id in self.org_ids:
            for fee_type in fee_types:
                fee_schedule = FeeSchedule(
                    id=f"fee_{org_id}_{fee_type}",
                    organisation_id=org_id,
                    fee_type=fee_type,
                    rate=random.uniform(0.01, 0.05),
                    min_fee=random.uniform(50, 500)
                )
                self.fixtures.fee_schedules.append(fee_schedule)

    def _plant_bugs(self) -> None:
        """Plant 3 bugs in the fixture data"""
        # Bug #1: NULL organisation_id in one contact row
        # We'll set organisation_id to None for one contact
        if self.fixtures.contacts:
            self.fixtures.contacts[0].organisation_id = None
            print(f"[BUG #1] Planted NULL organisation_id in contact: {self.fixtures.contacts[0].id}")

        # Bug #2: Duplicate business key within an organisation
        # We'll duplicate an account_number within the same organisation
        if len(self.fixtures.accounts) >= 2:
            # Find two accounts in the same organisation
            org_accounts = [a for a in self.fixtures.accounts if a.organisation_id == self.org_ids[0]]
            if len(org_accounts) >= 2:
                # Duplicate the account_number from the first to the second
                org_accounts[1].account_number = org_accounts[0].account_number
                print(f"[BUG #2] Planted duplicate account_number '{org_accounts[0].account_number}' in org {self.org_ids[0]}")

        # Bug #3: Cross-tenant leak
        # A holding in org A referencing a portfolio owned by org B
        if len(self.fixtures.holdings) >= 1 and len(self.fixtures.portfolios) >= 2:
            # Find a holding in org_1 and a portfolio in org_2
            org1_holdings = [h for h in self.fixtures.holdings if h.organisation_id == self.org_ids[0]]
            org2_portfolios = [p for p in self.fixtures.portfolios if p.organisation_id == self.org_ids[1]]
            if org1_holdings and org2_portfolios:
                # Make the holding reference the portfolio from a different org
                org1_holdings[0].portfolio_id = org2_portfolios[0].id
                print(f"[BUG #3] Planted cross-tenant leak: holding {org1_holdings[0].id} in org {self.org_ids[0]} references portfolio {org2_portfolios[0].id} from org {self.org_ids[1]}")


def main():
    """Main entry point"""
    print("Generating fixture data...")
    generator = FixtureGenerator()
    fixtures = generator.generate()
    fixtures.print_counts()
    print("Fixture generation complete.")
    print("\nBugs have been planted. See fixtures/PLANTED_BUGS.md for details.")


if __name__ == "__main__":
    main()
