"""
experiments/run_grounding_eval.py
---------------------------------
Evaluates Bidirectional Schema Linking and Backward Expressibility Validation.
Includes a labeled dataset of 30 queries (15 valid/expressible, 15 schema mismatches/hallucinations).
Performs threshold sensitivity analysis over tau in [0.10, 0.90].
Calculates Precision, Recall, F1, FPR, FNR, score distributions, and latency.
Outputs machine-readable JSON and CSV to experiments/results/.
"""

import os
import sys
import time
import json
import csv
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.knowledge.core.knowledge_base import KnowledgeBase
from src.knowledge.core.repository import KnowledgeRepository
from src.agents.query_understanding_agent import QueryUnderstandingAgent
from src.agents.schema_grounding_agent import SchemaGroundingAgent
from src.models.state import GraphState
from src.models.messages import MessageType

def get_labeled_dataset() -> List[Dict[str, Any]]:
    return [
        # --- 15 VALID / EXPRESSIBLE QUERIES (Ground Truth: Expressible = 1, Should NOT be objected to as mismatch) ---
        {"id": "V01", "db": "department_management", "query": "How many departments have a budget greater than 500000?", "is_expressible": True, "description": "Standard single-table metric query"},
        {"id": "V02", "db": "department_management", "query": "Which department has the highest budget in 2025?", "is_expressible": True, "description": "Ranking query with temporal and metric reference"},
        {"id": "V03", "db": "department_management", "query": "Show the names and ages of all department heads.", "is_expressible": True, "description": "Multi-attribute query on head table"},
        {"id": "V04", "db": "department_management", "query": "List all departments along with the name of their head manager.", "is_expressible": True, "description": "Multi-table join query (department + head + management)"},
        {"id": "V05", "db": "department_management", "query": "Find the average ranking of departments created after 1990.", "is_expressible": True, "description": "Aggregate with filter on Creation"},
        {"id": "V06", "db": "concert_singer", "query": "How many singers do we have?", "is_expressible": True, "description": "Singer table count query"},
        {"id": "V07", "db": "concert_singer", "query": "What is the average, minimum, and maximum age of all singers from France?", "is_expressible": True, "description": "Multi-aggregate with country filter"},
        {"id": "V08", "db": "concert_singer", "query": "Show names of stadiums with capacity between 5000 and 10000.", "is_expressible": True, "description": "Stadium capacity range filter"},
        {"id": "V09", "db": "concert_singer", "query": "List singers and the concerts they performed in.", "is_expressible": True, "description": "Three-table join across bridge table"},
        {"id": "V10", "db": "aircraft", "query": "Show all pilots of age between 30 and 40.", "is_expressible": True, "description": "Pilot entity and age attribute filter"},
        {"id": "V11", "db": "aircraft", "query": "List aircraft models and their manufacturers.", "is_expressible": True, "description": "Aircraft model and manufacturer attributes"},
        {"id": "V12", "db": "flight_2", "query": "Find all flights departing from New York.", "is_expressible": True, "description": "Flight origin airport query"},
        {"id": "V13", "db": "flight_2", "query": "What is the distance of flight 101?", "is_expressible": True, "description": "Flight distance metric"},
        {"id": "V14", "db": "pets_1", "query": "How many dogs are registered in the clinic?", "is_expressible": True, "description": "Pet type filter query"},
        {"id": "V15", "db": "pets_1", "query": "Find pet owners living in California.", "is_expressible": True, "description": "Owner address filter query"},

        # --- 15 INEXPRESSIBLE / SCHEMA MISMATCH QUERIES (Ground Truth: Inexpressible = 0, Genuine Mismatch) ---
        {"id": "M01", "db": "aircraft", "query": "Show all students enrolled in course science.", "is_expressible": False, "description": "Complete domain mismatch (student/course in aircraft DB)"},
        {"id": "M02", "db": "department_management", "query": "List all customer credit card transactions for October.", "is_expressible": False, "description": "Customer/transactions entity hallucination"},
        {"id": "M03", "db": "department_management", "query": "Find employee salaries and bonus percentages.", "is_expressible": False, "description": "Missing salary/bonus columns in department_management"},
        {"id": "M04", "db": "concert_singer", "query": "What is the fuel consumption and flight speed of each aircraft?", "is_expressible": False, "description": "Aircraft attributes queried in concert_singer DB"},
        {"id": "M05", "db": "concert_singer", "query": "Show patient blood pressure readings and medical history.", "is_expressible": False, "description": "Healthcare entities queried in music DB"},
        {"id": "M06", "db": "aircraft", "query": "Which professor has published the most papers?", "is_expressible": False, "description": "Academic entities queried in aviation DB"},
        {"id": "M07", "db": "flight_2", "query": "Show hotel reservations and room night rates for customers.", "is_expressible": False, "description": "Hotel reservation entities in flight DB"},
        {"id": "M08", "db": "pets_1", "query": "List stock prices and dividend yields for technology equities.", "is_expressible": False, "description": "Financial equity entities in pet clinic DB"},
        {"id": "M09", "db": "department_management", "query": "Show delivery tracking numbers and courier transit status.", "is_expressible": False, "description": "Logistics attributes in management DB"},
        {"id": "M10", "db": "concert_singer", "query": "Find the student grade point average in computer science.", "is_expressible": False, "description": "University GPA attributes in concert DB"},
        {"id": "M11", "db": "aircraft", "query": "List all restaurant menu items and prices.", "is_expressible": False, "description": "Restaurant menu entities in aircraft DB"},
        {"id": "M12", "db": "flight_2", "query": "What is the mortgage interest rate for residential borrowers?", "is_expressible": False, "description": "Banking mortgage attributes in flight DB"},
        {"id": "M13", "db": "pets_1", "query": "Show vehicle engine displacement and horsepower ratings.", "is_expressible": False, "description": "Automotive attributes in pet DB"},
        {"id": "M14", "db": "department_management", "query": "Find the weather forecast, wind speed, and humidity for tomorrow.", "is_expressible": False, "description": "Meteorological attributes in management DB"},
        {"id": "M15", "db": "concert_singer", "query": "Show inventory stock levels and warehouse reorder quantities.", "is_expressible": False, "description": "Supply chain warehouse attributes in concert DB"}
    ]

def evaluate_grounding_query(q_item: Dict[str, Any], kb: KnowledgeBase, qu_agent: QueryUnderstandingAgent, sg_agent: SchemaGroundingAgent) -> Dict[str, Any]:
    state = GraphState(
        original_request=q_item["query"],
        intent=q_item["query"],
        dialect="SQLite",
        database=q_item["db"],
        database_id=q_item["db"]
    )
    
    t0 = time.perf_counter()
    # Step 1: QueryUnderstanding
    qu_agent.act(state)
    
    # Step 2: SchemaGrounding
    msg = sg_agent.act(state)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    
    linking = state.schema_linking
    confidence = linking.confidence if linking else 0.0
    unmatched = linking.unmatched_concepts if linking else []
    tables = linking.final_tables if linking else []
    
    return {
        "id": q_item["id"],
        "database": q_item["db"],
        "query": q_item["query"],
        "is_expressible": q_item["is_expressible"],
        "confidence": round(confidence, 3),
        "unmatched_count": len(unmatched),
        "unmatched_concepts": unmatched,
        "selected_tables": tables,
        "latency_ms": round(latency_ms, 2)
    }

def main():
    os.makedirs("experiments/results", exist_ok=True)
    repo = KnowledgeRepository()
    kb = KnowledgeBase(repo)
    qu_agent = QueryUnderstandingAgent(kb=kb)
    sg_agent = SchemaGroundingAgent(kb=kb)
    
    dataset = get_labeled_dataset()
    print(f"Evaluating {len(dataset)} labeled queries for schema grounding & hallucination detection...")
    
    raw_evals = []
    for item in dataset:
        res = evaluate_grounding_query(item, kb, qu_agent, sg_agent)
        raw_evals.append(res)
        
    # Save raw evaluations
    with open("experiments/results/grounding_query_evals.json", "w") as f:
        json.dump(raw_evals, f, indent=2)
        
    with open("experiments/results/grounding_query_evals.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=raw_evals[0].keys())
        writer.writeheader()
        writer.writerows(raw_evals)
        
    # Threshold sensitivity sweep over tau in [0.10, 0.90]
    # Decision rule: Query is flagged as MISMATCH (Inexpressible) if confidence < tau OR unmatched_count > 0.
    thresholds = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
    sweep_results = []
    
    for tau in thresholds:
        tp = 0 # Inexpressible correctly detected as mismatch
        fp = 0 # Expressible mistakenly detected as mismatch
        tn = 0 # Expressible correctly accepted as expressible
        fn = 0 # Inexpressible missed (accepted as expressible)
        
        for r in raw_evals:
            ground_truth_mismatch = (not r["is_expressible"])
            predicted_mismatch = (r["confidence"] < tau or r["unmatched_count"] > 0)
            
            if ground_truth_mismatch and predicted_mismatch:
                tp += 1
            elif not ground_truth_mismatch and predicted_mismatch:
                fp += 1
            elif not ground_truth_mismatch and not predicted_mismatch:
                tn += 1
            elif ground_truth_mismatch and not predicted_mismatch:
                fn += 1
                
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
        accuracy = (tp + tn) / len(raw_evals)
        
        sweep_results.append({
            "threshold": tau,
            "TP": tp,
            "FP": fp,
            "TN": tn,
            "FN": fn,
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "false_positive_rate": round(fpr, 4),
            "false_negative_rate": round(fnr, 4)
        })
        
    # Save threshold sweep JSON & CSV
    with open("experiments/results/grounding_threshold_sweep.json", "w") as f:
        json.dump(sweep_results, f, indent=2)
        
    with open("experiments/results/grounding_threshold_sweep.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sweep_results[0].keys())
        writer.writeheader()
        writer.writerows(sweep_results)
        
    print("\n--- THRESHOLD SENSITIVITY SWEEP RESULTS ---")
    print(f"{'Threshold':<10} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10} | {'FPR':<10} | {'Accuracy':<10}")
    print("-" * 65)
    for s in sweep_results:
        print(f"{s['threshold']:<10.2f} | {s['precision']:<10.4f} | {s['recall']:<10.4f} | {s['f1_score']:<10.4f} | {s['false_positive_rate']:<10.4f} | {s['accuracy']:<10.4f}")

if __name__ == "__main__":
    main()
