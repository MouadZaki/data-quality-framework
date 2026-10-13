"""
Tests for auto-generation of tenant-related data quality checks.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from dq.autogen import generate_checks, _singular_to_plural, _infer_referenced_table, SHARED_REFERENCE_TABLES
from dq.schema import TableConfig, Check, CheckType, Severity
from dq.discovery import ConfigDiscovery
from dq.engine import QualityEngine
from dq.backends.fake import FakeBackend
from fixtures.generator import FixtureGenerator


class TestNamingConvention:
    """Tests for the naming convention used to infer referenced tables"""

    def test_singular_to_plural(self):
        """Test singular to plural conversion"""
        assert _singular_to_plural("portfolio") == "portfolios"
        assert _singular_to_plural("account") == "accounts"
        assert _singular_to_plural("advisor") == "advisors"
        assert _singular_to_plural("security") == "securities"
        assert _singular_to_plural("organisation") == "organisations"
        # Words ending in 's' stay the same
        assert _singular_to_plural("securities") == "securities"

    def test_infer_referenced_table(self):
        """Test inferring referenced table from column name"""
        assert _infer_referenced_table("portfolio_id") == "portfolios"
        assert _infer_referenced_table("account_id") == "accounts"
        assert _infer_referenced_table("advisor_id") == "advisors"
        assert _infer_referenced_table("security_id") == "securities"
        assert _infer_referenced_table("organisation_id") == "organisations"

    def test_infer_referenced_table_invalid(self):
        """Test that non-_id columns raise ValueError"""
        with pytest.raises(ValueError):
            _infer_referenced_table("name")
        with pytest.raises(ValueError):
            _infer_referenced_table("id")


class TestAutoGeneration:
    """Tests for auto-generation of checks"""

    def test_shared_reference_tables_constant(self):
        """Test that securities is in shared reference tables"""
        assert "securities" in SHARED_REFERENCE_TABLES

    def test_null_check_not_duplicated(self):
        """Test that null check is not generated if already exists"""
        table_config = TableConfig(
            table_name="accounts",
            tenant_column="organisation_id",
            checks=[
                Check(
                    name="account_org_id_not_null",
                    type=CheckType.NULL_CHECK,
                    config={"column": "organisation_id", "severity": "ERROR"},
                    enabled=True
                )
            ]
        )
        
        result = generate_checks([table_config])
        accounts_config = [tc for tc in result if tc.table_name == "accounts"][0]
        
        # Should have exactly 1 null check (the hand-written one)
        null_checks = [c for c in accounts_config.checks if c.type == CheckType.NULL_CHECK]
        assert len(null_checks) == 1
        assert null_checks[0].name == "account_org_id_not_null"

    def test_cross_tenant_check_not_duplicated(self):
        """Test that cross-tenant check is not generated if already exists"""
        table_config = TableConfig(
            table_name="holdings",
            tenant_column="organisation_id",
            checks=[
                Check(
                    name="holding_portfolio_cross_tenant",
                    type=CheckType.CROSS_TENANT_CHECK,
                    config={
                        "column": "portfolio_id",
                        "referenced_table": "portfolios",
                        "referenced_column": "id",
                        "severity": "ERROR"
                    },
                    enabled=True
                )
            ]
        )
        
        # Add portfolios config so it's recognized as tenant-owned
        portfolios_config = TableConfig(
            table_name="portfolios",
            tenant_column="organisation_id",
            checks=[]
        )
        
        result = generate_checks([table_config, portfolios_config])
        holdings_config = [tc for tc in result if tc.table_name == "holdings"][0]
        
        # Should have exactly 1 cross-tenant check (the hand-written one)
        ct_checks = [c for c in holdings_config.checks if c.type == CheckType.CROSS_TENANT_CHECK]
        assert len(ct_checks) == 1
        assert ct_checks[0].name == "holding_portfolio_cross_tenant"

    def test_auto_generated_checks_have_prefix(self):
        """Test that auto-generated checks have auto_ prefix"""
        table_config = TableConfig(
            table_name="accounts",
            tenant_column="organisation_id",
            checks=[
                Check(
                    name="account_id_unique_per_org",
                    type=CheckType.UNIQUE_KEY,
                    config={"columns": ["id"], "group_by": ["organisation_id"]},
                    enabled=True
                )
            ]
        )
        
        result = generate_checks([table_config])
        accounts_config = [tc for tc in result if tc.table_name == "accounts"][0]
        
        # Auto-generated checks should have auto_ prefix
        auto_checks = [c for c in accounts_config.checks if c.name.startswith("auto_")]
        assert len(auto_checks) > 0
        # All should have auto_ prefix
        for check in auto_checks:
            assert check.name.startswith("auto_")

    def test_shared_reference_table_gets_no_checks(self):
        """Test that shared reference tables don't get auto-generated tenant checks"""
        table_config = TableConfig(
            table_name="securities",
            tenant_column=None,  # No tenant column
            is_shared_reference=True,
            checks=[
                Check(
                    name="security_symbol_unique",
                    type=CheckType.UNIQUE_KEY,
                    config={"columns": ["symbol"]},
                    enabled=True
                )
            ]
        )
        
        result = generate_checks([table_config])
        securities_config = [tc for tc in result if tc.table_name == "securities"][0]
        
        # Should have only the hand-written check
        assert len(securities_config.checks) == 1
        assert securities_config.checks[0].name == "security_symbol_unique"


class TestAutoGenerationWithBackend:
    """Tests for auto-generation using the FakeBackend to get actual schema"""

    def test_auto_generated_catches_cross_tenant_leak(self):
        """Test that auto-generated checks catch the planted cross-tenant leak without hand-written check"""
        # Load fixtures
        generator = FixtureGenerator(verbose=False)
        fixtures = generator.generate()
        backend = FakeBackend(fixtures)
        
        # Create a modified holdings config without the hand-written cross-tenant check
        holdings_config = TableConfig(
            table_name="holdings",
            tenant_column="organisation_id",
            checks=[
                Check(
                    name="holding_id_unique_per_org",
                    type=CheckType.UNIQUE_KEY,
                    config={"columns": ["id"], "group_by": ["organisation_id"]},
                    enabled=True
                ),
                Check(
                    name="holding_org_id_not_null",
                    type=CheckType.NULL_CHECK,
                    config={"column": "organisation_id", "severity": "ERROR"},
                    enabled=True
                )
            ]
        )
        
        # Add other tenant-owned tables for reference
        portfolios_config = TableConfig(
            table_name="portfolios",
            tenant_column="organisation_id",
            checks=[]
        )
        
        # Apply auto-generation with backend
        result = generate_checks([holdings_config, portfolios_config], backend)
        holdings_result = [tc for tc in result if tc.table_name == "holdings"][0]
        
        # Should have auto-generated cross-tenant check
        auto_ct_checks = [c for c in holdings_result.checks if c.type == CheckType.CROSS_TENANT_CHECK and c.name.startswith("auto_")]
        assert len(auto_ct_checks) == 1
        assert auto_ct_checks[0].config["column"] == "portfolio_id"
        
        # Run the engine to verify it catches the bug
        engine = QualityEngine(backend)
        engine_result = engine.run_checks([holdings_result])
        
        # Find the auto-generated cross-tenant check result
        ct_result = [r for r in engine_result.check_results if r.check_name.startswith("auto_") and "cross_tenant" in r.check_name]
        assert len(ct_result) == 1
        assert ct_result[0].violation_count == 1  # Exactly 1 cross-tenant violation planted

    def test_brand_new_table_gets_checks_automatically(self):
        """Test that a brand-new table with no config gets checks automatically"""
        # Load fixtures
        generator = FixtureGenerator(verbose=False)
        fixtures = generator.generate()
        backend = FakeBackend(fixtures)
        
        # Create a new table config with minimal checks
        new_table_config = TableConfig(
            table_name="accounts",
            tenant_column="organisation_id",
            checks=[
                Check(
                    name="account_id_unique_per_org",
                    type=CheckType.UNIQUE_KEY,
                    config={"columns": ["id"], "group_by": ["organisation_id"]},
                    enabled=True
                )
            ]
        )
        
        # Add advisors config so it's recognized as tenant-owned
        advisors_config = TableConfig(
            table_name="advisors",
            tenant_column="organisation_id",
            checks=[]
        )
        
        # Apply auto-generation with backend
        result = generate_checks([new_table_config, advisors_config], backend)
        accounts_result = [tc for tc in result if tc.table_name == "accounts"][0]
        
        # Should have auto-generated null check on organisation_id
        auto_null_checks = [c for c in accounts_result.checks if c.type == CheckType.NULL_CHECK and c.name.startswith("auto_")]
        assert len(auto_null_checks) == 1
        assert auto_null_checks[0].config["column"] == "organisation_id"
        
        # Should have auto-generated cross-tenant check for advisor_id
        auto_ct_checks = [c for c in accounts_result.checks if c.type == CheckType.CROSS_TENANT_CHECK and c.name.startswith("auto_")]
        assert len(auto_ct_checks) >= 1  # At least advisor_id

    def test_real_configs_plus_autogen_report_3_bugs_no_false_failures(self):
        """Test that with real configs plus auto-generation, 3 bugs are reported with no false failures"""
        # Load fixtures
        generator = FixtureGenerator(verbose=False)
        fixtures = generator.generate()
        backend = FakeBackend(fixtures)
        
        # Load real configs
        discovery = ConfigDiscovery()
        table_configs = discovery.discover()
        
        # Apply auto-generation
        table_configs = generate_checks(table_configs, backend)
        
        # Run engine
        engine = QualityEngine(backend)
        result = engine.run_checks(table_configs)
        
        # Should have exactly 3 ERROR failures (the planted bugs)
        assert result.error_failures == 3
        assert result.warning_failures == 0
        
        # Verify the failures are the expected ones
        failed_check_names = [r.check_name for r in result.check_results if not r.passed and r.severity == Severity.ERROR]
        
        # The 3 planted bugs should be in the failures
        # 1. Duplicate account_number
        # 2. NULL organisation_id in contacts (hand-written check, not auto-generated)
        # 3. Cross-tenant portfolio reference in holdings
        assert any("account_number" in name for name in failed_check_names)
        # The contacts null check is hand-written, so it won't have "auto_" prefix
        assert any("contact" in name and "org_id" in name for name in failed_check_names)
        assert any("holding" in name and "portfolio" in name for name in failed_check_names)

    def test_null_org_id_not_counted_twice(self):
        """Test that NULL organisation_id in contacts is not counted twice by overlapping checks"""
        # Load fixtures
        generator = FixtureGenerator(verbose=False)
        fixtures = generator.generate()
        backend = FakeBackend(fixtures)
        
        # Create contacts config with both null check and potential cross-tenant check
        contacts_config = TableConfig(
            table_name="contacts",
            tenant_column="organisation_id",
            checks=[
                Check(
                    name="contact_id_unique_per_org",
                    type=CheckType.UNIQUE_KEY,
                    config={"columns": ["id"], "group_by": ["organisation_id"]},
                    enabled=True
                )
            ]
        )
        
        # Apply auto-generation with backend
        result = generate_checks([contacts_config], backend)
        contacts_result = [tc for tc in result if tc.table_name == "contacts"][0]
        
        # Should have auto-generated null check on organisation_id
        auto_null_checks = [c for c in contacts_result.checks if c.type == CheckType.NULL_CHECK and c.name.startswith("auto_")]
        assert len(auto_null_checks) == 1
        
        # Run engine
        engine = QualityEngine(backend)
        engine_result = engine.run_checks([contacts_result])
        
        # Find the null check result
        null_result = [r for r in engine_result.check_results if r.check_name.startswith("auto_") and "organisation_id" in r.check_name and "not_null" in r.check_name]
        assert len(null_result) == 1
        
        # Should count exactly 1 NULL (the planted bug)
        assert null_result[0].violation_count == 1
        
        # Cross-tenant checks should not count the NULL as a violation
        ct_results = [r for r in engine_result.check_results if "cross_tenant" in r.check_name]
        for ct_result in ct_results:
            # The NULL row should not be counted as a cross-tenant violation
            # because cross-tenant checks skip NULL tenant values
            assert ct_result.violation_count == 0
