import datetime
from src.knowledge.core.models import Provenance

def create_provenance(source: str, database_id: str = None, table: str = None, column: str = None, source_file: str = None) -> Provenance:
    """Helper to create a standard provenance record."""
    return Provenance(
        source=source,
        database_id=database_id,
        table=table,
        column=column,
        source_file=source_file,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
