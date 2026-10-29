import json
import os
import hashlib
from typing import Dict, Any, List

from src.knowledge.ingestion.base_ingestor import BaseDatasetIngestor
from src.knowledge.ingestion.sqlite_inspector import SQLiteInspector
from src.knowledge.core.models import (
    DatabaseSchema, TableSchema, ColumnSchema, Relationship,
    ColumnStatistics, Provenance
)
from src.knowledge.core.provenance import create_provenance

class SpiderIngestor(BaseDatasetIngestor):
    def __init__(self, spider_path: str = "spider_data", repo_path: str = "src/knowledge/stores"):
        super().__init__("spider", repo_path)
        self.spider_path = spider_path
        self.tables_json_path = os.path.join(spider_path, "tables.json")
        self.databases_path = os.path.join(spider_path, "database")
        self.discovered_dbs = []
        self.report_data = {
            "databases_discovered": 0,
            "databases_indexed": 0,
            "tables_indexed": 0,
            "relationships_indexed": 0,
            "errors": 0,
            "conflicts": 0,
            "skipped": 0
        }
        
    def _get_db_hash(self, db_path: str) -> str:
        """Calculate basic hash to detect if db changed."""
        if not os.path.exists(db_path):
            return ""
        stat = os.stat(db_path)
        return f"{stat.st_size}_{stat.st_mtime}"

    def discover(self) -> int:
        if not os.path.exists(self.tables_json_path):
            print(f"Error: {self.tables_json_path} not found.")
            return 0
            
        with open(self.tables_json_path, 'r', encoding='utf-8') as f:
            spider_data = json.load(f)
            
        for db_meta in spider_data:
            db_id = db_meta['db_id']
            db_file = os.path.join(self.databases_path, db_id, f"{db_id}.sqlite")
            if os.path.exists(db_file):
                self.discovered_dbs.append((db_id, db_file, db_meta))
                
        self.report_data["databases_discovered"] = len(self.discovered_dbs)
        return len(self.discovered_dbs)

    def ingest(self, limit: int = None) -> None:
        count = 0
        for db_id, db_file, spider_meta in self.discovered_dbs:
            if limit and count >= limit:
                break
                
            db_hash = self._get_db_hash(db_file)
            
            # Check if we already indexed this version (we store the hash in schema provenance)
            existing_schema = self.repo.get_schema(self.dataset_name, db_id)
            if existing_schema and existing_schema.provenance.timestamp == db_hash:
                self.report_data["skipped"] += 1
                continue
                
            try:
                self._ingest_database(db_id, db_file, spider_meta, db_hash)
                self.report_data["databases_indexed"] += 1
                count += 1
            except Exception as e:
                print(f"Error ingesting {db_id}: {e}")
                self.report_data["errors"] += 1

    def ingest_single(self, target_db_id: str) -> bool:
        """Dynamically ingests a single database by ID."""
        if not os.path.exists(self.tables_json_path):
            return False
            
        with open(self.tables_json_path, 'r', encoding='utf-8') as f:
            spider_data = json.load(f)
            
        for db_meta in spider_data:
            if db_meta['db_id'] == target_db_id:
                db_file = os.path.join(self.databases_path, target_db_id, f"{target_db_id}.sqlite")
                if not os.path.exists(db_file):
                    return False
                    
                db_hash = self._get_db_hash(db_file)
                try:
                    self._ingest_database(target_db_id, db_file, db_meta, db_hash)
                    self.report_data["databases_indexed"] += 1
                    return True
                except Exception as e:
                    print(f"Error dynamically ingesting {target_db_id}: {e}")
                    self.report_data["errors"] += 1
                    return False
                    
        return False

    def _ingest_database(self, db_id: str, db_file: str, spider_meta: Dict[str, Any], db_hash: str):
        with SQLiteInspector(db_file) as inspector:
            # 1. Cross-reference tables.json with SQLite metadata
            spider_tables = spider_meta['table_names_original']
            spider_columns = spider_meta['column_names_original']
            spider_col_types = spider_meta['column_types']
            spider_pks = spider_meta['primary_keys']
            spider_fks = spider_meta['foreign_keys']
            
            sqlite_tables = inspector.get_tables()
            
            schema = DatabaseSchema(
                database_id=db_id,
                tables={},
                provenance=Provenance(source="spider_ingestor", database_id=db_id, timestamp=db_hash)
            )
            
            relationships = []
            statistics = {}
            
            # Map Spider 0-indexed columns to Table/Col names
            def get_spider_col(idx: int):
                if idx == 0 or idx >= len(spider_columns): return None, None, None # 0 is usually *
                table_idx, col_name = spider_columns[idx]
                if table_idx < 0: return None, None, None
                table_name = spider_tables[table_idx]
                col_type = spider_col_types[idx]
                return table_name, col_name, col_type
            
            # Build tables
            for table_name in sqlite_tables:
                self.report_data["tables_indexed"] += 1
                sqlite_cols = inspector.get_columns(table_name)
                
                # Check for table conflict
                if table_name.lower() not in [t.lower() for t in spider_tables]:
                    self.report_data["conflicts"] += 1
                    
                table_schema = TableSchema(
                    name=table_name,
                    columns={},
                    primary_keys=[],
                    foreign_keys=[]
                )
                
                table_stats = {}
                row_count = inspector.get_row_count(table_name)
                skip_heavy_stats = row_count > 100000
                
                for col in sqlite_cols:
                    col_name = col['name']
                    # Use SQLite types primarily
                    table_schema.columns[col_name] = ColumnSchema(
                        name=col_name,
                        type=col['type'],
                        nullable=col['nullable'],
                        is_primary_key=col['is_primary_key'],
                        default_value=col['default_value']
                    )
                    
                    if col['is_primary_key']:
                        table_schema.primary_keys.append(col_name)
                        
                    # Stats
                    if not skip_heavy_stats:
                        stats = inspector.get_column_statistics(table_name, col_name, sample_limit=5)
                        if stats:
                            table_stats[col_name] = ColumnStatistics(**stats)
                            
                schema.tables[table_name] = table_schema
                if table_stats:
                    statistics[table_name] = table_stats

            # Extract FKs from SQLite first, then cross ref with Spider
            for table_name in sqlite_tables:
                sqlite_fks = inspector.get_foreign_keys(table_name)
                for fk in sqlite_fks:
                    schema.tables[table_name].foreign_keys.append(fk)
                    relationships.append(Relationship(
                        source_table=table_name,
                        source_column=fk['column'],
                        target_table=fk['target_table'],
                        target_column=fk['target_column'],
                        relationship_type="foreign_key",
                        source="sqlite"
                    ))
                    self.report_data["relationships_indexed"] += 1
                    
            # Check Spider FKs
            for source_idx, target_idx in spider_fks:
                s_tab, s_col, _ = get_spider_col(source_idx)
                t_tab, t_col, _ = get_spider_col(target_idx)
                if s_tab and t_tab:
                    # check if already found
                    found = False
                    for r in relationships:
                        if r.source_table.lower() == s_tab.lower() and r.target_table.lower() == t_tab.lower() and r.source_column.lower() == s_col.lower():
                            found = True
                            break
                    if not found:
                        relationships.append(Relationship(
                            source_table=s_tab,
                            source_column=s_col,
                            target_table=t_tab,
                            target_column=t_col,
                            relationship_type="foreign_key",
                            source="spider_tables_json"
                        ))
                        self.report_data["relationships_indexed"] += 1
                        # If table exists, add to schema
                        if s_tab in schema.tables:
                            schema.tables[s_tab].foreign_keys.append({
                                "column": s_col,
                                "target_table": t_tab,
                                "target_column": t_col
                            })
                            
            # Save all
            self.repo.save_schema(self.dataset_name, db_id, schema)
            self.repo.save_relationships(self.dataset_name, db_id, relationships)
            if statistics:
                self.repo.save_statistics(self.dataset_name, db_id, statistics)

    def validate(self) -> Dict[str, Any]:
        return {"status": "ok", "conflicts": self.report_data["conflicts"]}

    def report(self) -> Dict[str, Any]:
        return self.report_data
