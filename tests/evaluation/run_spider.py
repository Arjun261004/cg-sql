import os
import sys

# Add root project to sys path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from main import setup_registry
from src.core.orchestrator import Orchestrator
from src.models.state import GraphState

def run_spider_eval(question: str, db_path: str):
    print(f"\n{'='*50}\nEVALUATING ON SPIDER DATABASE\n{'='*50}")
    print(f"Database: {db_path}")
    print(f"Question: {question}\n")
    
    import re
    from src.knowledge.core.knowledge_base import KnowledgeBase
    from src.knowledge.core.repository import KnowledgeRepository

    db_id_match = re.search(r'database/([^/]+)/', db_path)
    database_id = db_id_match.group(1) if db_id_match else "department_management"

    kb_repo = KnowledgeRepository()
    kb = KnowledgeBase(kb_repo)
    registry = setup_registry(kb=kb)
    orchestrator = Orchestrator(registry, kb=kb)
    
    initial_state = GraphState(
        original_request=question,
        intent=question,
        dialect="SQLite",
        database=database_id,
        database_id=database_id,
        db_path=db_path
    )
    
    final_state = orchestrator.run(initial_state)
    
    print("\n--- FINAL RESULT ---")
    print(f"Generated SQL: {final_state.final_sql}")
    print(f"Confidence: {final_state.final_confidence}")
    if final_state.execution_results:
        print(f"Execution Output: {final_state.execution_results[-1]}")
    
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_spider.py <path_to_sqlite_db> <natural_language_question>")
        sys.exit(1)
        
    db_path = sys.argv[1]
    question = " ".join(sys.argv[2:])
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        sys.exit(1)
        
    run_spider_eval(question, db_path)
