export interface AgentEvent {
  agent: string;
  message_type: 'proposal' | 'objection' | 'request' | 'evidence' | 'decision' | 'rejection';
  capability?: string;
  claim: string;
  evidence: any[];
  confidence: number;
  target_agents: string[];
  timestamp: string;
}

export interface SQLResponse {
  request_id: string;
  status: string;
  sql: string;
  confidence: number;
  answer: string;
  events: AgentEvent[];
  execution_data?: {
    status: string;
    rows?: number;
    columns?: string[];
    data?: any[][];
    error?: string;
  };
  knowledge_evidence?: any[];
  risk_evaluation?: {
    candidate_evaluations: any[];
    selected_candidate_id: string;
    selected_candidate_type: string;
    decision_rationale: string;
    confidence: number;
    risk_factors?: string[];
    hedging_strategy?: string;
  };
  decision_history?: any[];
  query_plans?: any[];
}

export const generateSQL = async (question: string, database: string, dialect: string): Promise<SQLResponse> => {
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  
  const response = await fetch(`${apiUrl}/generate-sql`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question, database, dialect }),
  });
  
  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }
  
  return response.json();
};

export interface DatabaseOption {
  id: string;
  name: string;
  db_id?: string;
  tables?: string[];
}

export const getDatabases = async (): Promise<DatabaseOption[]> => {
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  
  const response = await fetch(`${apiUrl}/databases`);
  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }
  
  const data = await response.json();
  const list: DatabaseOption[] = data.databases || [];
  return list.filter(d => d.db_id !== 'college_2' && !d.id.includes('college_2'));
};
