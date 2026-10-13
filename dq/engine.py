"""
Data quality engine with database interface and check execution.
Enforces counts-only rule and ERROR vs WARNING handling.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from dq.schema import TableConfig, Check, CheckType, Severity


@dataclass
class CheckResult:
    """Result of a single check execution"""
    check_name: str
    table_name: str
    passed: bool
    violation_count: int
    severity: Severity
    message: str


@dataclass
class EngineResult:
    """Result of engine execution"""
    total_checks: int
    passed_checks: int
    failed_checks: int
    warning_failures: int
    error_failures: int
    check_results: List[CheckResult]
    should_halt: bool


class DatabaseBackend(ABC):
    """Abstract database interface for quality checks"""

    @abstractmethod
    def get_row_count(self, table_name: str) -> int:
        """Get total row count for a table"""
        pass

    @abstractmethod
    def count_null_values(self, table_name: str, column: str) -> int:
        """Count NULL values in a column"""
        pass

    @abstractmethod
    def count_duplicate_keys(
        self,
        table_name: str,
        columns: List[str],
        group_by: Optional[List[str]] = None
    ) -> int:
        """Count duplicate key violations"""
        pass

    @abstractmethod
    def count_cross_tenant_violations(
        self,
        table_name: str,
        column: str,
        referenced_table: str,
        referenced_column: str,
        tenant_column: str
    ) -> int:
        """Count cross-tenant reference violations"""
        pass

    @abstractmethod
    def count_range_violations(
        self,
        table_name: str,
        column: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None
    ) -> int:
        """Count values outside specified range"""
        pass

    def get_table_columns(self, table_name: str) -> List[str]:
        """
        Get column names for a table.
        
        Returns only column names (metadata), never data values.
        This is safe for the counts-only rule.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of column names
        """
        raise NotImplementedError("get_table_columns not implemented")


class QualityEngine:
    """Data quality engine that executes checks through DB interface"""

    def __init__(self, backend: DatabaseBackend):
        """
        Initialize engine with a database backend
        
        Args:
            backend: Database backend implementation
        """
        self.backend = backend

    def run_checks(self, table_configs: List[TableConfig]) -> EngineResult:
        """
        Run all checks for given table configurations
        
        Args:
            table_configs: List of table configurations with checks
            
        Returns:
            EngineResult with check outcomes
        """
        check_results = []
        total_checks = 0
        passed_checks = 0
        failed_checks = 0
        warning_failures = 0
        error_failures = 0

        for table_config in table_configs:
            for check in table_config.checks:
                if not check.enabled:
                    continue

                total_checks += 1
                result = self._execute_check(table_config, check)
                check_results.append(result)

                if result.passed:
                    passed_checks += 1
                else:
                    failed_checks += 1
                    if result.severity == Severity.WARNING:
                        warning_failures += 1
                    else:
                        error_failures += 1

        should_halt = error_failures > 0

        return EngineResult(
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            warning_failures=warning_failures,
            error_failures=error_failures,
            check_results=check_results,
            should_halt=should_halt
        )

    def _execute_check(self, table_config: TableConfig, check: Check) -> CheckResult:
        """
        Execute a single check
        
        Args:
            table_config: Table configuration
            check: Check to execute
            
        Returns:
            CheckResult with violation count and outcome
        """
        check_type = check.type
        config = check.config

        try:
            if check_type == CheckType.NULL_CHECK:
                return self._execute_null_check(table_config.table_name, check)
            elif check_type == CheckType.UNIQUE_KEY:
                return self._execute_unique_key_check(table_config.table_name, check)
            elif check_type == CheckType.CROSS_TENANT_CHECK:
                return self._execute_cross_tenant_check(table_config.table_name, check, table_config)
            elif check_type == CheckType.ROW_COUNT_RECONCILIATION:
                return self._execute_row_count_check(table_config.table_name, check)
            elif check_type == CheckType.RANGE_CHECK:
                return self._execute_range_check(table_config.table_name, check)
            else:
                return CheckResult(
                    check_name=check.name,
                    table_name=table_config.table_name,
                    passed=False,
                    violation_count=0,
                    severity=Severity.ERROR,
                    message=f"Unknown check type: {check_type}"
                )
        except Exception as e:
            # Only include exception type name, not message, to prevent leaking query text or data
            # Execution failures are treated as ERROR severity to halt the pipeline on unexpected issues
            return CheckResult(
                check_name=check.name,
                table_name=table_config.table_name,
                passed=False,
                violation_count=0,
                severity=Severity.ERROR,
                message=f"Check execution failed: {type(e).__name__}"
            )

    def _execute_null_check(self, table_name: str, check: Check) -> CheckResult:
        """Execute null_check - counts only, no raw rows"""
        column = check.config["column"]
        severity = Severity(check.config.get("severity", "ERROR"))
        
        violation_count = self.backend.count_null_values(table_name, column)
        passed = violation_count == 0
        
        return CheckResult(
            check_name=check.name,
            table_name=table_name,
            passed=passed,
            violation_count=violation_count,
            severity=severity,
            message=f"NULL check on {column}: {violation_count} violations"
        )

    def _execute_unique_key_check(self, table_name: str, check: Check) -> CheckResult:
        """Execute unique_key check - counts only, no raw rows"""
        columns = check.config["columns"]
        group_by = check.config.get("group_by")
        severity = Severity(check.config.get("severity", "ERROR"))
        
        violation_count = self.backend.count_duplicate_keys(table_name, columns, group_by)
        passed = violation_count == 0
        
        return CheckResult(
            check_name=check.name,
            table_name=table_name,
            passed=passed,
            violation_count=violation_count,
            severity=severity,
            message=f"Unique key check on {columns}: {violation_count} violations"
        )

    def _execute_cross_tenant_check(self, table_name: str, check: Check, table_config: TableConfig) -> CheckResult:
        """Execute cross_tenant_check - counts only, no raw rows"""
        column = check.config["column"]
        referenced_table = check.config["referenced_table"]
        referenced_column = check.config["referenced_column"]
        severity = Severity(check.config.get("severity", "ERROR"))
        tenant_column = table_config.tenant_column  # Use table's tenant column
        
        violation_count = self.backend.count_cross_tenant_violations(
            table_name, column, referenced_table, referenced_column, tenant_column
        )
        passed = violation_count == 0
        
        return CheckResult(
            check_name=check.name,
            table_name=table_name,
            passed=passed,
            violation_count=violation_count,
            severity=severity,
            message=f"Cross-tenant check on {column}: {violation_count} violations"
        )

    def _execute_row_count_check(self, table_name: str, check: Check) -> CheckResult:
        """Execute row_count_reconciliation - counts only"""
        expected_count = check.config["expected_count"]
        severity = Severity(check.config.get("severity", "ERROR"))
        
        actual_count = self.backend.get_row_count(table_name)
        violation_count = abs(actual_count - expected_count)
        passed = actual_count == expected_count
        
        return CheckResult(
            check_name=check.name,
            table_name=table_name,
            passed=passed,
            violation_count=violation_count,
            severity=severity,
            message=f"Row count check: expected {expected_count}, got {actual_count}"
        )

    def _execute_range_check(self, table_name: str, check: Check) -> CheckResult:
        """Execute range_check - counts only, no raw rows"""
        column = check.config["column"]
        min_value = check.config.get("min_value")
        max_value = check.config.get("max_value")
        severity = Severity(check.config.get("severity", "ERROR"))
        
        violation_count = self.backend.count_range_violations(table_name, column, min_value, max_value)
        passed = violation_count == 0
        
        return CheckResult(
            check_name=check.name,
            table_name=table_name,
            passed=passed,
            violation_count=violation_count,
            severity=severity,
            message=f"Range check on {column}: {violation_count} violations"
        )

    def print_results(self, result: EngineResult) -> None:
        """Print engine results in a readable format"""
        print("\n" + "="*60)
        print("DATA QUALITY CHECK RESULTS")
        print("="*60)
        print(f"Total checks: {result.total_checks}")
        print(f"Passed: {result.passed_checks}")
        print(f"Failed: {result.failed_checks}")
        print(f"  - Warnings: {result.warning_failures}")
        print(f"  - Errors: {result.error_failures}")
        print("="*60)
        
        for check_result in result.check_results:
            status = "✓ PASS" if check_result.passed else "✗ FAIL"
            severity = f"[{check_result.severity.value}]"
            print(f"{status} {severity} {check_result.table_name}.{check_result.check_name}")
            print(f"      {check_result.message}")
        
        print("="*60)
        
        if result.should_halt:
            print("HALT: Error-level checks failed. Pipeline should stop.")
        else:
            print("CONTINUE: No error-level failures.")
        print("="*60 + "\n")
