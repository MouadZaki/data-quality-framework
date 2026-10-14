# Data Quality Runbooks

This guide explains how to interpret data quality check failures and how to fix them. It's written for new team members who need to understand what the checks mean and how to investigate issues.

## Table of Contents

- [Understanding Check Types](#understanding-check-types)
- [ERROR vs WARNING](#error-vs-warning)
- [The HALT Message and Exit Code](#the-halt-message-and-exit-code)
- [Auto-Generated Checks](#auto-generated-checks)
- [The Counts-Only Rule](#the-counts-only-rule)
- [Using the Validator](#using-the-validator)
- [Check-Specific Runbooks](#check-specific-runbooks)

---

## Understanding Check Types

### null_check

**What it means:** A `null_check` detects NULL (missing) values in a critical column. For example, every account should have an `organisation_id` - if it's NULL, we don't know which tenant owns it.

**How to read the output:**
```
✗ FAIL [ERROR] contacts.contact_org_id_not_null
      NULL check on organisation_id: 1 violations
```
This means 1 row in the `contacts` table has a NULL `organisation_id`.

**Likely causes:**
- Data migration didn't populate the column
- Application bug that doesn't set the value on insert
- ETL process skipping the column
- Database schema change allowing NULLs when it shouldn't

**Step-by-step remediation:**
1. Identify which rows have NULL values by querying the database directly (not through the quality framework):
   ```sql
   SELECT * FROM contacts WHERE organisation_id IS NULL;
   ```
2. Determine the correct value for each NULL row (e.g., from source data, business logic, or default value)
3. Update the rows with the correct values:
   ```sql
   UPDATE contacts SET organisation_id = 'correct_value' WHERE id = 'row_id';
   ```
4. If the column should never be NULL, consider adding a NOT NULL constraint to the database schema
5. Re-run the quality check to verify the fix

---

### unique_key

**What it means:** A `unique_key` check ensures that a business key is unique within a tenant. For example, `account_number` should be unique within each organisation - two accounts in the same organisation shouldn't have the same number.

**How to read the output:**
```
✗ FAIL [ERROR] accounts.account_number_unique_per_org
      Unique key check on ['account_number']: 1 violations
```
This means 1 duplicate `account_number` exists within an organisation.

**Likely causes:**
- Data entry error (manual duplicate)
- Application bug allowing duplicates
- Missing unique constraint in database
- Race condition in concurrent inserts
- Data migration creating duplicates

**Step-by-step remediation:**
1. Find the duplicate rows:
   ```sql
   SELECT account_number, COUNT(*) 
   FROM accounts 
   GROUP BY account_number 
   HAVING COUNT(*) > 1;
   ```
2. For each duplicate, determine which row is correct (e.g., based on creation date, last modified, or business rules)
3. Delete or merge the duplicate rows:
   ```sql
   DELETE FROM accounts WHERE id = 'duplicate_row_id';
   ```
4. Add a unique constraint to the database to prevent future duplicates:
   ```sql
   ALTER TABLE accounts ADD CONSTRAINT unique_account_number_per_org 
   UNIQUE (account_number, organisation_id);
   ```
5. Re-run the quality check to verify the fix

---

### cross_tenant_check

**What it means:** A `cross_tenant_check` detects data crossing tenant boundaries. For example, a holding in `org_001` shouldn't reference a portfolio that belongs to `org_002`. This is a critical security check to prevent data leaks.

**How to read the output:**
```
✗ FAIL [ERROR] holdings.holding_portfolio_cross_tenant
      Cross-tenant check on portfolio_id: 1 violations
```
This means 1 holding references a portfolio from a different organisation.

**Likely causes:**
- Application bug allowing cross-tenant references
- Data migration mixing tenant data
- Missing foreign key constraints
- User with access to multiple tenants accidentally mixing data
- API endpoint not validating tenant ownership

**Step-by-step remediation:**
1. Find the violating rows:
   ```sql
   SELECT h.id, h.portfolio_id, h.organisation_id as holding_org, 
          p.organisation_id as portfolio_org
   FROM holdings h
   JOIN portfolios p ON h.portfolio_id = p.id
   WHERE h.organisation_id != p.organisation_id;
   ```
2. For each violation, determine the correct tenant:
   - Should the holding belong to the portfolio's tenant?
   - Should the portfolio belong to the holding's tenant?
   - Is one of the rows completely wrong?
3. Update the data to fix the tenant mismatch:
   ```sql
   UPDATE holdings SET organisation_id = 'correct_tenant_id' WHERE id = 'holding_id';
   ```
4. Add database constraints to prevent future violations (e.g., foreign keys with tenant filtering)
5. Review application code to ensure tenant validation on all writes
6. Re-run the quality check to verify the fix

---

### row_count_reconciliation

**What it means:** A `row_count_reconciliation` check validates that a table has the expected number of rows. This is useful for detecting data loss, incomplete ETL loads, or unexpected data growth.

**How to read the output:**
```
✗ FAIL [ERROR] organisations.org_row_count
      Row count check: expected 3, got 2
```
This means the table has 2 rows but we expected 3.

**Likely causes:**
- ETL process failed partway through
- Data was accidentally deleted
- Expected count is outdated
- Data source changed
- Database replication issue

**Step-by-step remediation:**
1. Verify the actual row count:
   ```sql
   SELECT COUNT(*) FROM organisations;
   ```
2. Check if the expected count in the config is still correct:
   - Has the business changed? Do we expect more/ fewer organisations now?
   - Update the config if the expected count needs to change
3. If rows are missing, investigate:
   - Check ETL logs for errors
   - Check database logs for deletions
   - Compare with source data
4. If rows were deleted in error, restore from backup or re-run ETL
5. Re-run the quality check to verify the fix

---

### range_check

**What it means:** A `range_check` validates that numeric values fall within an acceptable range. For example, fee rates should be between 0% and 5%, or account balances should be non-negative.

**How to read the output:**
```
✗ FAIL [WARNING] fee_schedules.fee_rate_range
      Range check on rate: 2 violations
```
This means 2 rows have `rate` values outside the specified range.

**Likely causes:**
- Data entry error (typo)
- Business rules changed but check wasn't updated
- Calculation error in application
- Data migration with incorrect values
- Edge case not considered in range definition

**Step-by-step remediation:**
1. Find the violating rows:
   ```sql
   SELECT * FROM fee_schedules 
   WHERE rate < 0 OR rate > 5;
   ```
2. Determine the correct values:
   - Are these typos that should be fixed?
   - Are they legitimate edge cases that need the range updated?
3. Fix the data or update the check config as appropriate
4. If the range needs to change, update the YAML config:
   ```yaml
   - name: fee_rate_range
     type: range_check
     config:
       column: rate
       min_value: 0
       max_value: 10  # Updated range
       severity: WARNING
   ```
5. Re-run the quality check to verify the fix

---

## ERROR vs WARNING

**ERROR** checks are critical failures that should halt the data pipeline. These indicate data quality issues that could lead to:
- Security violations (cross-tenant data leaks)
- Business logic errors (duplicate keys causing incorrect calculations)
- Data integrity issues (NULL values in required fields)

When ERROR checks fail, the runner exits with code 1 and displays:
```
HALT: Error-level checks failed. Pipeline should stop.
```

**WARNING** checks are informational failures that should be reviewed but don't halt the pipeline. These indicate:
- Potential issues that need investigation
- Edge cases that might be acceptable
- Data that's outside normal bounds but not necessarily wrong

When only WARNING checks fail, the runner exits with code 0 and the pipeline continues.

**Best practice:** Treat ERROR failures as blocking issues that must be fixed before proceeding. Review WARNING failures and decide whether to fix them or adjust the check configuration.

---

## The HALT Message and Exit Code

The runner displays a HALT message when ERROR-level checks fail:

```
============================================================
HALT: Error-level checks failed. Pipeline should stop.
============================================================
```

This message means:
- One or more ERROR checks failed
- The runner will exit with code 1
- Your CI/CD pipeline or data pipeline should stop
- Do not proceed with data processing until the issues are fixed

**Exit codes:**
- `0`: All checks passed, or only WARNING checks failed
- `1`: One or more ERROR checks failed

**In CI/CD:** Configure your pipeline to fail when the runner exits with code 1. This prevents bad data from being processed.

---

## Auto-Generated Checks

Auto-generated checks are prefixed with `auto_` in their names:

```
✓ PASS [ERROR] accounts.auto_advisor_id_cross_tenant
      Cross-tenant check on advisor_id: 0 violations
```

These checks are automatically generated by the framework for:
- Null checks on tenant columns (e.g., `organisation_id`)
- Cross-tenant checks on foreign-key-style columns (e.g., `advisor_id` → `advisors`)

**Why they exist:** To provide baseline tenant isolation checks without requiring manual configuration for every table.

**How to read them:** Same as hand-written checks - the `auto_` prefix just indicates it was generated automatically.

**Overriding auto-generated checks:** If you need different behavior for an auto-generated check, add a hand-written check with the same column and type. The hand-written check will take precedence and no duplicate will be generated.

**Disabling auto-generation:** If you don't want auto-generated checks, run the runner with `--no-autogen`:
```bash
python -m dq --no-autogen
```

---

## The Counts-Only Rule

**Why raw rows never appear in logs:**
This framework follows a strict "counts-only" rule to protect customer privacy. Quality checks return only counts (e.g., "3 violations"), never the actual row data. This prevents PII (Personally Identifiable Information) from leaking into logs, CI systems, or error messages.

**How to investigate safely:**
When you need to see the actual violating rows:

1. **Connect directly to the database** (not through the quality framework)
2. **Use appropriate access controls** - ensure you have permission to view the data
3. **Query for the specific violations** based on the check type:
   ```sql
   -- For null_check
   SELECT * FROM table WHERE column IS NULL LIMIT 10;
   
   -- For unique_key
   SELECT column, COUNT(*) FROM table 
   GROUP BY column HAVING COUNT(*) > 1;
   
   -- For cross_tenant_check
   SELECT t1.id, t1.column, t1.organisation_id, t2.organisation_id
   FROM table t1 JOIN referenced_table t2 ON t1.column = t2.id
   WHERE t1.organisation_id != t2.organisation_id;
   ```
4. **Never export the full result set** - use LIMIT and review only what you need
5. **Never paste customer data into tickets, chats, or documentation**

**Security benefit:** Even if logs are leaked or CI systems are compromised, no customer data is exposed because only counts are stored.

---

## Using the Validator

The validator checks your YAML configuration files for errors before you run the quality checks. It catches typos, missing fields, and logical inconsistencies.

**Run the validator:**
```bash
python -m dq.validate
```

**What it checks:**
- Invalid YAML syntax
- Invalid check types
- Missing required fields (table_name, checks, name, type, config fields)
- Duplicate table names across files
- Duplicate check names within a table
- Cross-tenant checks referencing tables that don't exist in configs
- Checks on columns that don't exist in the database schema
- Tenant-owned tables without a tenant_column defined
- Row count reconciliation with non-positive expected counts

**Output when valid:**
```
✓ All configurations are valid
```
Exit code: 0

**Output when invalid:**
```
✗ Found 3 validation error(s):

File: configs/accounts.yml
  Table: accounts
  Check: account_check
  Error: Invalid check type: 'invalid_type'. Valid types: ['null_check', 'unique_key', 'cross_tenant_check', 'row_count_reconciliation', 'range_check']

File: configs/holdings.yml
  Table: holdings
  Check: holding_check
  Error: cross_tenant_check references table 'portfolios' which is not defined in any config file

File: configs/contacts.yml
  Table: contacts
  Check: null
  Error: Column 'nonexistent_column' does not exist in table 'contacts'
```
Exit code: 1

**In CI:** The validator runs before tests in the GitHub Actions workflow. This ensures configuration errors are caught early.

**Best practice:** Always run the validator after editing configs, and before committing changes.

---

## Check-Specific Runbooks

### Summary Table

| Check Type | Severity | What It Detects | Common Causes |
|------------|----------|-----------------|---------------|
| null_check | ERROR | Missing values in critical columns | Migration issues, app bugs, schema changes |
| unique_key | ERROR | Duplicate business keys within tenant | Data entry, missing constraints, race conditions |
| cross_tenant_check | ERROR | Data crossing tenant boundaries | App bugs, migration errors, missing validation |
| row_count_reconciliation | ERROR | Unexpected row counts | ETL failures, data loss, outdated expectations |
| range_check | WARNING | Values outside acceptable range | Typos, business rule changes, edge cases |

### Quick Reference

**For immediate action:**
1. ERROR failures → Stop pipeline, fix before proceeding
2. WARNING failures → Review, decide if fix needed
3. Auto-generated failures → Same as hand-written, just auto-created
4. Validator failures → Fix config before running checks

**For investigation:**
1. Use direct database queries (not the framework)
2. Follow the check-specific runbook above
3. Update configs if business rules changed
4. Add database constraints to prevent recurrence

**For prevention:**
1. Run validator before committing configs
2. Add database constraints (NOT NULL, UNIQUE, FOREIGN KEY)
3. Review application code for tenant validation
4. Keep expected counts up to date
