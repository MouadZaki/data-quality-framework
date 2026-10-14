# Data Quality & Testing Framework

An extensible data quality testing framework for wealth management data that catches corrupt records, duplicate keys, and cross-tenant data collisions before bad data reaches dashboards.

## Overview

This framework provides:
- **Database-agnostic quality checks** that run against any backend
- **Multi-tenancy boundary enforcement** via `organisation_id`
- **Counts-only validation** to prevent PII leakage into logs
- **ERROR vs WARNING severity** to control pipeline halting behavior
- **Auto-generated tenant checks** for cross-tenant collision detection

## Project Structure

```
configs/            YAML test declarations per table
dq/
  schema.py         Declaration model + validation
  discovery.py      Walks configs/, builds executable test objects
  engine.py         Runs checks through the DB interface
  backends/         Fake (unit tests) + ClickHouse backends
  autogen.py        Auto-generated default tenant checks
fixtures/           Data generator + PLANTED_BUGS.md
tests/              Unit tests (no database needed)
docs/runbooks.md    Failure definitions + remediation steps
```

## Supported Checks

- `null_check` - Detect NULL values in critical columns
- `unique_key` - Enforce business key uniqueness within tenant
- `cross_tenant_check` - Detect data crossing tenant boundaries
- `row_count_reconciliation` - Validate expected row counts
- `range_check` - Validate numeric ranges

## Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Development Phases

This project is built in phases:
1. **Phase 0**: Setup (repo layout, venv, requirements, README)
2. **Phase 1**: Fixtures (10 tables, 3 planted bugs, data generator)
3. **Phase 2**: Declarations (YAML schema + discovery module)
4. **Phase 3**: Engine (DB interface, fake backend, runner, unit tests)
5. **Phase 4**: ClickHouse (Docker container, real backend, load fixtures)
6. **Phase 5**: Auto checks (generator of default tenant checks)
7. **Phase 6**: CI + docs (validator CLI, GitHub Actions, runbooks)
8. **Phase 7**: Demo (break-and-catch walkthrough script)

## Testing

```bash
# Run unit tests (no database required)
pytest tests/

# Run with coverage
pytest tests/ --cov=dq --cov-report=html
```

## Configuration Validation

Before running quality checks, validate your YAML configuration files to catch errors early:

```bash
# Validate all configs in configs/
python -m dq.validate
```

The validator checks for:
- Invalid YAML syntax
- Invalid check types
- Missing required fields
- Duplicate table or check names
- Cross-tenant checks referencing nonexistent tables
- Checks on columns that don't exist in the schema
- Tenant-owned tables without a tenant column
- Invalid row count expectations

Exit code 0 indicates valid configs, exit code 1 indicates errors.

## Continuous Integration

The project uses GitHub Actions for CI. On every pull request and push to main, the workflow:
1. Sets up Python 3.13
2. Installs dependencies from requirements.txt
3. Runs the configuration validator (`python -m dq.validate`)
4. Runs the full test suite (`python -m pytest`)

ClickHouse tests are automatically skipped in CI since no Docker service is needed for the unit tests. This ensures fast feedback on configuration errors and code changes without requiring a database.

## Running Quality Checks

### Using the Fake Backend (No Database Required)

```bash
# Run quality checks on fixture data using the fake backend
python -m dq
```

This loads the real configurations from `configs/`, runs all checks against the generated fixture data, and prints the results. The command exits with code 1 if any ERROR-level checks fail, and code 0 if only WARNING-level checks fail or all checks pass.

### Using ClickHouse Backend

```bash
# Start ClickHouse container
docker-compose up -d

# Generate CSV fixtures
python fixtures/generator.py

# Load fixtures into ClickHouse
python scripts/load_clickhouse.py

# Run quality checks against ClickHouse
python -m dq --backend clickhouse
```

The ClickHouse backend runs the same checks against real data in ClickHouse and should detect the same 3 planted bugs with identical counts and exit code 1.

### Auto-Generated Tenant Checks

The framework can automatically generate tenant-related checks for tables that have a `tenant_column` defined. This includes:

1. **Null checks** on the tenant column (e.g., `organisation_id`)
2. **Cross-tenant checks** for foreign-key-style columns ending in `_id` that reference other tenant-owned tables

#### Naming Convention for Foreign Key Inference

Auto-generation uses a naming convention to infer referenced tables from column names:

- Foreign key columns ending in `_id` map to tables by converting to plural:
  - `portfolio_id` → `portfolios`
  - `account_id` → `accounts`
  - `advisor_id` → `advisors`
  - `organisation_id` → `organisations`
  - etc.

#### Shared Reference Tables

Shared reference tables (like `securities`) are excluded from auto-generation because they don't have a tenant column and are shared across all tenants.

#### Running with Auto-Generation

```bash
# Run with auto-generation enabled (default)
python -m dq

# Run without auto-generation
python -m dq --no-autogen
```

Auto-generated checks are prefixed with `auto_` in their names to distinguish them from hand-written checks in the output. If a hand-written check already covers the same column and type, no duplicate is generated.

## Hard Rules

1. **Counts only** - Quality checks return counts/totals only, never raw customer rows
2. **Database-agnostic** - Engine talks to a DB interface; unit tests use fake in-memory backend
3. **ERROR vs WARNING** - Failed ERROR checks halt the run; WARNING checks only log alerts
4. **Build from scratch** - No dependence on existing codebases; Python 3.11+
5. **One phase at a time** - Complete each phase before moving to the next
6. **Git workflow** - One branch per phase, small clear commits, PRs to main

## Important Notes

### Cross-Tenant Checks and NULL Values

Cross-tenant checks compare the `organisation_id` of the referencing row with the `organisation_id` of the referenced row to detect data crossing tenant boundaries. If the referencing row has a NULL `organisation_id`, the cross-tenant check cannot perform the comparison and does not count it as a cross-tenant violation. Instead, NULL `organisation_id` values are caught by separate `null_check` configurations. This ensures that the "exactly 3 violations" in the fixture data (1 NULL org_id, 1 duplicate key, 1 cross-tenant reference) are unambiguous and each violation type is detected by its appropriate check.

## License

MIT