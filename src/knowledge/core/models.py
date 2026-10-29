from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class Provenance(BaseModel):
    source: str
    database_id: Optional[str] = None
    table: Optional[str] = None
    column: Optional[str] = None
    source_file: Optional[str] = None
    timestamp: Optional[str] = None

class ColumnSchema(BaseModel):
    name: str
    type: str
    nullable: bool = True
    is_primary_key: bool = False
    default_value: Optional[Any] = None

class TableSchema(BaseModel):
    name: str
    columns: Dict[str, ColumnSchema]
    primary_keys: List[str]
    foreign_keys: List[Dict[str, str]] = Field(default_factory=list) # e.g. {"column": "id", "target_table": "other", "target_column": "id"}

class DatabaseMetadata(BaseModel):
    dataset: str
    database_id: str
    engine: str
    dialect: str
    database_path: str
    source: str
    schema_version: str

class DatabaseSchema(BaseModel):
    database_id: str
    tables: Dict[str, TableSchema]
    provenance: Provenance

class Relationship(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str = "foreign_key"
    source: str = "metadata"
    confidence: float = 1.0

class ColumnStatistics(BaseModel):
    distinct_count: Optional[int] = None
    null_count: Optional[int] = None
    sample_values: List[Any] = Field(default_factory=list)
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None

class DialectRules(BaseModel):
    dialect: str
    supported_functions: List[str] = Field(default_factory=list)
    date_syntax: str = ""
    string_functions: str = ""
    identifier_quoting: str = ""
    known_restrictions: List[str] = Field(default_factory=list)

class SQLRule(BaseModel):
    category: str
    pattern: str
    description: str
    severity: str = "error"

class ErrorRule(BaseModel):
    error_type: str
    pattern: str
    diagnostic_steps: List[str] = Field(default_factory=list)
    repair_strategies: List[str] = Field(default_factory=list)

class BusinessDefinition(BaseModel):
    term: str
    definition: str
    sql_logic: str = ""
    source: str = ""
    version: str = "1.0"
    confidence: float = 1.0
