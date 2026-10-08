"""
YAML declaration schema with Pydantic validation.
Defines the structure for data quality check configurations.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    """Check severity levels"""
    ERROR = "ERROR"
    WARNING = "WARNING"


class CheckType(str, Enum):
    """Supported check types"""
    NULL_CHECK = "null_check"
    UNIQUE_KEY = "unique_key"
    CROSS_TENANT_CHECK = "cross_tenant_check"
    ROW_COUNT_RECONCILIATION = "row_count_reconciliation"
    RANGE_CHECK = "range_check"


class NullCheckConfig(BaseModel):
    """Configuration for null_check"""
    column: str = Field(..., description="Column to check for NULL values")
    severity: Severity = Field(default=Severity.ERROR, description="Severity level")


class UniqueKeyConfig(BaseModel):
    """Configuration for unique_key check"""
    columns: List[str] = Field(..., description="Columns that form the business key")
    group_by: Optional[List[str]] = Field(default=None, description="Columns to group by (e.g., organisation_id)")
    severity: Severity = Field(default=Severity.ERROR, description="Severity level")


class CrossTenantCheckConfig(BaseModel):
    """Configuration for cross_tenant_check"""
    column: str = Field(..., description="Column to check for cross-tenant references")
    referenced_table: str = Field(..., description="Table being referenced")
    referenced_column: str = Field(..., description="Column in referenced table")
    severity: Severity = Field(default=Severity.ERROR, description="Severity level")


class RowCountReconciliationConfig(BaseModel):
    """Configuration for row_count_reconciliation"""
    expected_count: int = Field(..., description="Expected row count")
    severity: Severity = Field(default=Severity.ERROR, description="Severity level")


class RangeCheckConfig(BaseModel):
    """Configuration for range_check"""
    column: str = Field(..., description="Column to check")
    min_value: Optional[float] = Field(default=None, description="Minimum allowed value")
    max_value: Optional[float] = Field(default=None, description="Maximum allowed value")
    severity: Severity = Field(default=Severity.ERROR, description="Severity level")


class Check(BaseModel):
    """A single quality check"""
    name: str = Field(..., description="Unique name for the check")
    type: CheckType = Field(..., description="Type of check")
    config: Dict[str, Any] = Field(..., description="Check-specific configuration")
    description: Optional[str] = Field(default=None, description="Human-readable description")
    enabled: bool = Field(default=True, description="Whether the check is enabled")

    @field_validator("config")
    def validate_config_by_type(cls, v, info):
        """Validate config based on check type"""
        check_type = info.data.get("type")
        if check_type == CheckType.NULL_CHECK:
            NullCheckConfig(**v)
        elif check_type == CheckType.UNIQUE_KEY:
            UniqueKeyConfig(**v)
        elif check_type == CheckType.CROSS_TENANT_CHECK:
            CrossTenantCheckConfig(**v)
        elif check_type == CheckType.ROW_COUNT_RECONCILIATION:
            RowCountReconciliationConfig(**v)
        elif check_type == CheckType.RANGE_CHECK:
            RangeCheckConfig(**v)
        return v


class TableConfig(BaseModel):
    """Configuration for a single table"""
    table_name: str = Field(..., description="Name of the table")
    checks: List[Check] = Field(default_factory=list, description="List of quality checks")
    description: Optional[str] = Field(default=None, description="Table description")
    tenant_column: Optional[str] = Field(default="organisation_id", description="Column used for multi-tenancy")
    is_shared_reference: bool = Field(default=False, description="Whether this is a shared reference table (no tenant column)")


class ConfigManifest(BaseModel):
    """Manifest of all table configurations"""
    tables: List[TableConfig] = Field(default_factory=list, description="All table configurations")
    version: str = Field(default="1.0", description="Config schema version")
