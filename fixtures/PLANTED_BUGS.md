# Planted Bugs in Fixture Data

This document describes the 3 intentionally planted bugs in the fixture data for testing the data quality framework.

## Bug #1: NULL organisation_id

**Table**: `contacts`  
**Key**: `cnt_acc_org_001_1` (first contact record)  
**Reason**: One contact has a NULL `organisation_id`, violating the multi-tenancy boundary requirement that all tenant-owned tables must have a valid `organisation_id`.

**Expected detection**: `null_check` on `contacts.organisation_id` with severity ERROR.

---

## Bug #2: Duplicate Business Key

**Table**: `accounts`  
**Key**: Duplicate `account_number` within the same organisation  
**Reason**: Two accounts in the same organisation share the same `account_number` (business key), violating uniqueness constraints within a tenant.

**Expected detection**: `unique_key` check on `accounts.account_number` grouped by `organisation_id` with severity ERROR.

---

## Bug #3: Cross-Tenant Leak

**Table**: `holdings`  
**Key**: A holding in `org_001` references a portfolio owned by `org_002`  
**Reason**: A holding record belongs to one organisation but its `portfolio_id` references a portfolio from a different organisation, creating a cross-tenant data leak that violates isolation boundaries.

**Expected detection**: `cross_tenant_check` on `holdings.portfolio_id` referencing `portfolios.id` with severity ERROR.

---

## Verification

To verify these bugs are present after running the generator:

```bash
python fixtures/generator.py
```

The generator will print confirmation messages when each bug is planted.
