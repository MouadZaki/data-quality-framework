# Planted Bugs in Fixture Data

This document describes the 3 intentionally planted bugs in the fixture data for testing the data quality framework.

## Bug #1: NULL organisation_id

**Table**: `contacts`  
**Row ID**: `cnt_acc_org_001_1` (first contact record)  
**Column**: `organisation_id`  
**Value**: `NULL` (empty string in CSV)  
**Reason**: One contact has a NULL `organisation_id`, violating the multi-tenancy boundary requirement that all tenant-owned tables must have a valid `organisation_id`.

**Expected detection**: `null_check` on `contacts.organisation_id` with severity ERROR.

---

## Bug #2: Duplicate Business Key

**Table**: `accounts`  
**Column**: `account_number`  
**Duplicate value**: `ORG_001-0001`  
**Affected rows**: Two accounts in `org_001` share the same `account_number`  
**Reason**: Two accounts in the same organisation share the same `account_number` (business key), violating uniqueness constraints within a tenant.

**Expected detection**: `unique_key` check on `accounts.account_number` grouped by `organisation_id` with severity ERROR.

---

## Bug #3: Cross-Tenant Leak

**Table**: `holdings`  
**Row ID**: `hld_prt_acc_org_001_1_sec_006_0`  
**Column**: `portfolio_id`  
**Value**: `prt_acc_org_002_1`  
**Holding organisation**: `org_001`  
**Referenced portfolio organisation**: `org_002`  
**Reason**: A holding record belongs to one organisation but its `portfolio_id` references a portfolio from a different organisation, creating a cross-tenant data leak that violates isolation boundaries.

**Expected detection**: `cross_tenant_check` on `holdings.portfolio_id` referencing `portfolios.id` with severity ERROR.

---

## Verification

### Automated Verification

Run the verification script to confirm all 3 bugs are present:

```bash
python fixtures/verify_bugs.py
```

### Unit Tests

Run the fixture tests to verify exactly 3 violations exist:

```bash
pytest tests/test_fixtures.py -v
```

### Manual Verification

Generate fixtures and review the output:

```bash
python fixtures/generator.py
```

The generator will:
- Print confirmation messages when each bug is planted
- Write CSV files to `fixtures/output/` with NULL values as empty strings
- Print row counts for all tables

### CSV Output Files

After running the generator, the following CSV files are created in `fixtures/output/`:
- `organisations.csv`
- `advisors.csv`
- `accounts.csv`
- `contacts.csv` (contains Bug #1: NULL organisation_id)
- `securities.csv`
- `portfolios.csv`
- `holdings.csv` (contains Bug #3: cross-tenant reference)
- `transactions.csv`
- `trades.csv`
- `fee_schedules.csv`
