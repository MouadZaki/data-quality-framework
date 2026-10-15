# Demo Video Script

This document provides the exact script for recording the demo video, including commands, expected output, and talking points for review questions.

## Video Outline

1. Introduction and overview
2. Unit tests without database connection
3. Live data break and engine catching it (demo script)
4. Counts-only rule demonstration
5. Conclusion

---

## Part 1: Introduction

**Talking Point:**
"This is the Data Quality Framework for wealth management data. It catches corrupt records, duplicate keys, and cross-tenant data collisions before bad data reaches dashboards."

**Key Points:**
- Database-agnostic quality checks
- Multi-tenancy boundary enforcement
- Counts-only validation (no PII in logs)
- ERROR vs WARNING severity
- Auto-generated tenant checks

---

## Part 2: Unit Tests Without Database Connection

**Command:**
```bash
python -m pytest tests/ -v
```

**Expected Output:**
```
==================================================== test session starts ====================================================
platform win32 -- Python 3.13.2
...
tests/test_engine.py::TestQualityEngine::test_backend_row_count PASSED
tests/test_engine.py::TestQualityEngine::test_backend_count_null_values PASSED
tests/test_engine.py::TestQualityEngine::test_backend_count_duplicate_keys PASSED
...
tests/test_demo.py::TestDemoFakeBackend::test_step_0_clean_data PASSED
tests/test_demo.py::TestDemoFakeBackend::test_step_1_duplicate_key PASSED
...
tests/test_counts_only.py::test_demo_output_counts_only PASSED
...
===================================================== 80 passed, 11 skipped in 15.22s =====================================================
```

**Review Question: "Does your unit test suite run without a database connection?"**

**Answer:**
"Yes. The entire test suite runs using the FakeBackend, which is an in-memory implementation. No Docker container, no ClickHouse, no external database. All 80 tests pass in 15 seconds. This makes the tests fast, reliable, and easy to run in CI."

**Key Points:**
- FakeBackend uses fixture data in memory
- No external dependencies
- Fast feedback loop
- CI-friendly

---

## Part 3: Live Data Break and Engine Catching It

**Command:**
```bash
python -m dq.demo --pause
```

**Expected Output - Step 0 (Clean Data):**
```
======================================================================
DATA QUALITY FRAMEWORK DEMO - FAKE BACKEND
======================================================================

This demo shows how the engine catches various data quality issues.
Each step starts from clean data, injects one corruption,
and runs the quality checks.

======================================================================
STEP 0: Clean Data
======================================================================
Generating clean fixtures (no planted bugs)...

✓ PASS [ERROR] accounts.account_number_unique_per_org
      Unique key check on ['account_number']: 0 violations
✓ PASS [ERROR] contacts.contact_org_id_not_null
      NULL check on organisation_id: 0 violations
...
Total checks: 27
Errors: 0
Warnings: 0

✓ OK: All checks pass, CONTINUE, exit code 0
```

**Talking Point:**
"Step 0 shows clean data. All 27 checks pass with 0 violations. The engine exits with code 0, meaning CONTINUE."

**Expected Output - Step 1 (Duplicate Key):**
```
======================================================================
STEP 1: Duplicate Business Key
======================================================================
Injecting: duplicate account_number in one organisation
  Duplicated account_number 'ORG_001-0001' in org_001

✗ FAIL [ERROR] accounts.account_number_unique_per_org
      Unique key check on ['account_number']: 1 violations
...
Total checks: 27
Errors: 1
Warnings: 0

============================================================
HALT: Error-level checks failed. Pipeline should stop.
============================================================

✓ OK: Only account_number_unique check fails, HALT, exit code 1
```

**Talking Point:**
"Step 1 injects a duplicate account_number. The unique_key check catches it with 1 violation. The engine halts with exit code 1."

**Expected Output - Step 2 (NULL Required Field):**
```
======================================================================
STEP 2: Missing Required Field
======================================================================
Injecting: NULL organisation_id in advisors table
  Set organisation_id to NULL for advisor adv_org_001_1

✗ FAIL [ERROR] advisors.advisor_org_id_not_null
      NULL check on organisation_id: 1 violations
...
Total checks: 27
Errors: 1
Warnings: 0

============================================================
HALT: Error-level checks failed. Pipeline should stop.
============================================================

✓ OK: NULL org_id check fails, HALT, exit code 1
```

**Talking Point:**
"Step 2 injects a NULL organisation_id. The null_check catches it. The engine halts."

**Expected Output - Step 3 (Cross-Tenant Leak):**
```
======================================================================
STEP 3: Cross-Tenant Leak
======================================================================
Injecting: holding pointing to another organisation's portfolio
  Holding hld_prt_acc_org_001_1_sec_001_0 in org_001 now references portfolio prt_acc_org_002_1 from org_002

✗ FAIL [ERROR] holdings.holding_portfolio_cross_tenant
      Cross-tenant check on portfolio_id: 1 violations
...
Total checks: 27
Errors: 1
Warnings: 0

============================================================
HALT: Error-level checks failed. Pipeline should stop.
============================================================

✓ OK: Cross-tenant check fails, HALT, exit code 1
```

**Talking Point:**
"Step 3 injects a cross-tenant leak - a holding in org_001 referencing a portfolio in org_002. This is a critical security issue. The cross_tenant_check catches it immediately."

**Expected Output - Step 4 (Auto-Generated Checks):**
```
======================================================================
STEP 4: Auto-Generated Checks
======================================================================
Injecting: trade whose account_id belongs to another organisation
(trades table has no hand-written cross-tenant check)
  Trade trd_acc_org_001_1_1 in org_001 now references account acc_org_002_1 from org_002

--- Running with auto-generation ON ---
✗ FAIL [ERROR] trades.auto_account_id_cross_tenant
      Cross-tenant check on account_id: 1 violations
...
Total checks: 27
Errors: 1
Warnings: 0

============================================================
HALT: Error-level checks failed. Pipeline should stop.
============================================================

--- Running with auto-generation OFF (--no-autogen) ---
✓ PASS [ERROR] trades.trade_check
      Null check on security_id: 0 violations
...
Total checks: 20
Errors: 0
Warnings: 0

✓ OK: Auto-generation catches the leak, --no-autogen misses it
```

**Talking Point:**
"Step 4 shows the power of auto-generated checks. The trades table has no hand-written cross-tenant check, but the framework auto-generates one. With auto-generation ON, the leak is caught. With --no-autogen, it's missed. This provides baseline tenant isolation without manual configuration."

**Expected Output - Step 5 (WARNING-Only):**
```
======================================================================
STEP 5: WARNING-Only Problem
======================================================================
Injecting: fee rate outside allowed range
  Set fee rate to 15% (outside 0-10% range) for fee_org_001_Management

✗ FAIL [WARNING] fee_schedules.fee_rate_range
      Range check on rate: 1 violations
...
Total checks: 27
Errors: 0
Warnings: 1

✓ OK: WARNING logged, run continues, exit code 0
```

**Talking Point:**
"Step 5 injects a WARNING-level problem - a fee rate outside the allowed range. The check fails as a WARNING, but the run continues with exit code 0. This allows for informational issues without halting the pipeline."

**Review Question: "Show a live data break and the engine catching it"**

**Answer:**
"The demo script shows exactly this. Each step injects a specific corruption - duplicate keys, NULL values, cross-tenant leaks - and the engine catches it immediately with counts-only output. The engine halts on ERROR-level failures and continues on WARNING-level failures."

**Key Points:**
- Step-by-step corruption injection
- Immediate detection
- Counts-only output (no raw data)
- HALT on ERROR, CONTINUE on WARNING

---

## Part 4: Counts-Only Rule Demonstration

**Command:**
```bash
python -m pytest tests/test_counts_only.py -v
```

**Expected Output:**
```
tests/test_counts_only.py::test_demo_output_counts_only PASSED
```

**Talking Point:**
"The counts-only test proves that the engine output contains no fixture row IDs, account numbers, emails, or any customer data. Only violation counts and check names appear. This prevents PII leakage into logs, CI systems, or error messages."

**Review Question: "How does your engine prevent raw row leakage in log files?"**

**Answer:**
"The engine follows a strict counts-only rule. Quality checks return only counts (e.g., '1 violation'), never the actual row data. The test suite includes a dedicated test that asserts no fixture row IDs or values appear in the output. Even if logs are leaked or CI systems are compromised, no customer data is exposed."

**Key Points:**
- Checks return counts only
- No SELECT * in investigation queries
- Test suite validates counts-only compliance
- Security benefit: no PII in logs

---

## Part 5: ClickHouse Demo

**Command:**
```bash
docker-compose up -d
python -m dq.demo --backend clickhouse
```

**Expected Output:**
```
======================================================================
DATA QUALITY FRAMEWORK DEMO - CLICKHOUSE BACKEND
======================================================================

This demo runs against a real ClickHouse database.
Using separate database 'dq_demo' to avoid affecting main tables.

✓ Created database 'dq_demo'

Loading clean data into dq_demo...
  Loaded 3 rows into organisations
  Loaded 6 rows into advisors
  Loaded 75 rows into accounts
  ...
✓ Clean data loaded

======================================================================
STEP 0: Clean Data
======================================================================
Running checks on clean data...
✓ PASS [ERROR] accounts.account_number_unique_per_org
      Unique key check on ['account_number']: 0 violations
...
Total checks: 27
Errors: 0
Warnings: 0

✓ OK: All checks pass, CONTINUE, exit code 0
...
```

**Talking Point:**
"The ClickHouse demo runs the same steps against a real database. It uses a separate 'dq_demo' database so the main tables are never touched. The same corruptions are injected using ClickHouse ALTER TABLE mutations, and the engine catches them identically."

---

## Summary Commands

**Run unit tests (no database):**
```bash
python -m pytest tests/ -v
```

**Run demo (fake backend):**
```bash
python -m dq.demo
```

**Run demo with pause (for video):**
```bash
python -m dq.demo --pause
```

**Run demo (ClickHouse):**
```bash
docker-compose up -d
python -m dq.demo --backend clickhouse
```

**Run quality checks (fake backend):**
```bash
python -m dq
```

**Run quality checks (ClickHouse):**
```bash
python -m dq --backend clickhouse
```

**Validate configs:**
```bash
python -m dq.validate
```

---

## Review Questions - Quick Reference

**Q: Does your unit test suite run without a database connection?**
A: Yes. All tests use FakeBackend (in-memory). 80 tests pass in 15 seconds with no external dependencies.

**Q: Show a live data break and the engine catching it.**
A: The demo script injects corruptions step-by-step (duplicate keys, NULL values, cross-tenant leaks) and the engine catches each one with counts-only output.

**Q: How does your engine prevent raw row leakage in log files?**
A: Strict counts-only rule. Checks return only violation counts, never row data. Dedicated test validates no fixture IDs or values appear in output.
