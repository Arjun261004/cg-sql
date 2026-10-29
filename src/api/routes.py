from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import os

from src.core.orchestrator import Orchestrator
from src.models.state import GraphState
from main import setup_registry

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SQLRequest(BaseModel):
    question: str
    database: str = "default"
    dialect: str = "DuckDB"

from src.knowledge.core.knowledge_base import KnowledgeBase
from src.knowledge.core.repository import KnowledgeRepository

# Initialize KB once for the app
kb_repo = KnowledgeRepository()
knowledge_base = KnowledgeBase(kb_repo)

# Explicitly excluded databases/schemas
EXCLUDED_DBS = {"college_2"}

@app.post("/generate-sql")
async def generate_sql(req: SQLRequest):
    import os, re, json
    from fastapi import HTTPException

    # Extract db_id and resolve db_path
    req_db = req.database.strip()
    db_id_match = re.search(r'database/([^/]+)/', req_db)
    if db_id_match:
        db_id = db_id_match.group(1)
    elif os.path.exists(f"./spider_data/database/{req_db}/{req_db}.sqlite"):
        db_id = req_db
    elif os.path.exists(req_db):
        db_id = os.path.splitext(os.path.basename(req_db))[0]
    else:
        db_id = req_db if req_db and req_db != "default" else "department_management"

    schemas_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge", "stores", "schemas", "spider")
    allowed_dbs = {
        f[:-5] for f in os.listdir(schemas_dir)
        if f.endswith(".json") and f[:-5] not in EXCLUDED_DBS
    } if os.path.exists(schemas_dir) else set()

    if db_id not in allowed_dbs:
        raise HTTPException(
            status_code=400,
            detail=f"Database '{db_id}' is not supported. Supported schemas are: {', '.join(sorted(allowed_dbs))}"
        )

    db_path = f"./spider_data/database/{db_id}/{db_id}.sqlite"
    if not os.path.exists(db_path):
        raise HTTPException(
            status_code=404,
            detail=f"SQLite database file not found for '{db_id}' at {db_path}"
        )

    registry = setup_registry(kb=knowledge_base)
    orchestrator = Orchestrator(registry, kb=knowledge_base)
    
    initial_state = GraphState(
        original_request=req.question,
        intent=req.question,
        database=db_id,
        database_id=db_id,
        dataset="spider",
        dialect=req.dialect,
        db_path=db_path
    )
    
    final_state = orchestrator.run(initial_state)
    
    # Serialize messages
    events = []
    for msg in final_state.agent_messages:
        events.append({
            "agent": msg.agent,
            "message_type": msg.message_type,
            "capability": getattr(msg, "capability", ""),
            "claim": msg.claim,
            "evidence": msg.evidence,
            "confidence": msg.confidence,
            "target_agents": msg.target_agents,
            "timestamp": "2026-09-07T12:00:00Z" # Mock timestamp for UI
        })
        
    # Get final execution result if available
    execution_data = None
    if final_state.execution_results:
        execution_data = final_state.execution_results[-1]

    return {
        "request_id": str(uuid.uuid4()),
        "status": "completed",
        "sql": final_state.final_sql,
        "confidence": final_state.final_confidence,
        "answer": final_state.final_answer,
        "events": events,
        "execution_data": execution_data,
        "knowledge_evidence": final_state.knowledge_evidence,
        "risk_evaluation": final_state.risk_evaluation.dict() if final_state.risk_evaluation else None,
        "decision_history": final_state.decision_history,
        "query_plans": final_state.query_plans
    }

@app.get("/databases")
async def list_databases():
    import json
    schemas_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge", "stores", "schemas", "spider")
    if not os.path.exists(schemas_dir):
        return {"databases": []}
        
    databases = []
    for file_name in sorted(os.listdir(schemas_dir)):
        if file_name.endswith(".json"):
            db_id = file_name[:-5]
            if db_id in EXCLUDED_DBS:
                continue
            schema_path = os.path.join(schemas_dir, file_name)
            tables = []
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema_data = json.load(f)
                    tables = list(schema_data.get("tables", {}).keys())
            except Exception:
                tables = []

            sqlite_path = f"./spider_data/database/{db_id}/{db_id}.sqlite"
            databases.append({
                "id": sqlite_path,
                "db_id": db_id,
                "name": f"Spider: {db_id.replace('_', ' ').title()}",
                "tables": tables
            })
            
    return {"databases": databases}
