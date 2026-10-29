import { useState, useEffect } from 'react';
import { 
  Database, Play, AlertTriangle, CheckCircle, Clock, Info, 
  ChevronRight, Shield, Wrench, Search, Code, Check, Sparkles, Layers
} from 'lucide-react';
import { generateSQL, getDatabases, type AgentEvent, type SQLResponse, type DatabaseOption } from './api/client';

const SIX_AGENTS = [
  { id: 'QueryUnderstandingAgent', name: 'Query Understanding', icon: Search, desc: 'Intent & conceptual grounding' },
  { id: 'SchemaGroundingAgent', name: 'Schema Grounding', icon: Database, desc: 'Bidirectional linking & ER reasoning' },
  { id: 'SQLGenerationAgent', name: 'SQL Generation', icon: Code, desc: 'Relational planning & candidate generation' },
  { id: 'ValidationExecutionAgent', name: 'Validation & Execution', icon: Layers, desc: 'Static checks, DB execution & verification' },
  { id: 'RepairAgent', name: 'Repair Agent', icon: Wrench, desc: 'Rule-first MAPLEDoctor & LLM repair' },
  { id: 'RiskHedgingAgent', name: 'Risk Hedging', icon: Shield, desc: 'Candidate comparison & safe selection' }
];

function App() {
  const [question, setQuestion] = useState('How many departments have a budget greater than 500000?');
  const [database, setDatabase] = useState('./spider_data/database/department_management/department_management.sqlite');
  const [dialect, setDialect] = useState('SQLite');
  const [isGenerating, setIsGenerating] = useState(false);
  
  // State for dynamic databases
  const [availableDatabases, setAvailableDatabases] = useState<DatabaseOption[]>([]);

  useEffect(() => {
    getDatabases().then((dbs) => {
      setAvailableDatabases(dbs);
      if (dbs.length > 0 && !dbs.some(d => d.id === database)) {
        setDatabase(dbs[0].id);
      }
    }).catch(console.error);
  }, []);
  
  // State for streaming/rendering results
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [currentEventIndex, setCurrentEventIndex] = useState(-1);
  const [finalResult, setFinalResult] = useState<SQLResponse | null>(null);

  const handleGenerate = async () => {
    setIsGenerating(true);
    setEvents([]);
    setCurrentEventIndex(-1);
    setFinalResult(null);
    
    try {
      const response = await generateSQL(question, database, dialect);
      setEvents(response.events);
      
      for (let i = 0; i < response.events.length; i++) {
        setTimeout(() => {
          setCurrentEventIndex(i);
          if (i === response.events.length - 1) {
            setFinalResult(response);
            setIsGenerating(false);
          }
        }, i * 650);
      }
      
      if (response.events.length === 0) {
        setFinalResult(response);
        setIsGenerating(false);
      }
      
    } catch (error) {
      console.error(error);
      setIsGenerating(false);
    }
  };

  const getEventIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case 'objection': return <AlertTriangle className="w-5 h-5 text-amber-500" />;
      case 'decision': return <CheckCircle className="w-5 h-5 text-emerald-500" />;
      case 'evidence': return <Info className="w-5 h-5 text-blue-500" />;
      default: return <ChevronRight className="w-5 h-5 text-indigo-400" />;
    }
  };

  const getEventStyle = (type: string) => {
    switch (type.toLowerCase()) {
      case 'objection': return 'border-l-4 border-amber-500 bg-amber-50/60';
      case 'decision': return 'border-l-4 border-emerald-500 bg-emerald-50/50';
      case 'evidence': return 'border-l-4 border-blue-500 bg-blue-50/40';
      default: return 'border-l-4 border-slate-300 bg-white';
    }
  };

  const getAgentStatus = (agentId: string) => {
    const visibleEvents = events.slice(0, currentEventIndex + 1);
    const agentEvents = visibleEvents.filter(e => e.agent === agentId);
    if (agentEvents.length > 0) {
      const last = agentEvents[agentEvents.length - 1];
      if (last.message_type === 'objection' || last.message_type === 'rejection') return 'objection';
      return 'completed';
    }
    if (isGenerating) {
      const lastVisible = visibleEvents[visibleEvents.length - 1];
      if (lastVisible && lastVisible.target_agents?.includes(agentId)) {
        return 'active';
      }
    }
    if (!isGenerating && finalResult) {
      return 'completed';
    }
    return 'pending';
  };

  return (
    <div className="min-h-screen flex flex-col font-sans bg-slate-100 text-slate-900">
      {/* HEADER */}
      <header className="bg-slate-950 text-white px-6 py-4 shadow-lg border-b border-slate-800 flex justify-between items-center">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-600 rounded-lg shadow-md shadow-blue-500/20">
              <Database className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
                CG-SQL
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  Six-Agent Architecture
                </span>
              </h1>
              <p className="text-xs text-slate-400">Concept-Grounded Multi-Agent SQL Synthesizer with Shared Blackboard & Knowledge Layer</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs bg-slate-900 px-3 py-1.5 rounded-full border border-slate-800">
            <span className="relative flex h-2.5 w-2.5">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isGenerating ? 'bg-amber-400' : 'bg-emerald-400'}`}></span>
              <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${isGenerating ? 'bg-amber-500' : 'bg-emerald-500'}`}></span>
            </span>
            <span className="font-medium text-slate-300">{isGenerating ? 'Agents Synthesizing...' : 'System Ready'}</span>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* LEFT PANEL: Inputs & Final Output */}
        <div className="w-2/5 p-6 bg-white border-r border-slate-200 flex flex-col gap-6 overflow-y-auto shadow-sm">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2">
              Natural-Language Query
            </label>
            <textarea 
              className="w-full border border-slate-300 rounded-lg p-3 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none resize-none h-28 transition-all"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question about your database..."
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2">Database / Schema</label>
              <select 
                className="w-full border border-slate-300 rounded-lg p-2.5 text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white font-medium text-slate-800"
                value={database}
                onChange={(e) => setDatabase(e.target.value)}
              >
                {availableDatabases.length === 0 ? (
                  <option value="./spider_data/database/department_management/department_management.sqlite">Spider: Department Management</option>
                ) : (
                  availableDatabases.map(db => (
                    <option key={db.id} value={db.id}>
                      {db.name} {db.tables && db.tables.length > 0 ? `(${db.tables.join(', ')})` : ''}
                    </option>
                  ))
                )}
              </select>
              {(() => {
                const selected = availableDatabases.find(d => d.id === database);
                if (!selected?.tables || selected.tables.length === 0) return null;
                return (
                  <div className="mt-2">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                      Available Tables ({selected.tables.length}):
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {selected.tables.map(tbl => (
                        <span 
                          key={tbl}
                          className="text-[11px] bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-mono border border-slate-200"
                        >
                          {tbl}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2">SQL Dialect</label>
              <select 
                className="w-full border border-slate-300 rounded-lg p-2.5 text-xs focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                value={dialect}
                onChange={(e) => setDialect(e.target.value)}
              >
                <option value="SQLite">SQLite</option>
                <option value="DuckDB">DuckDB</option>
                <option value="Snowflake">Snowflake</option>
                <option value="BigQuery">BigQuery</option>
              </select>
            </div>
          </div>

          <button 
            onClick={handleGenerate}
            disabled={isGenerating || !question.trim()}
            className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white py-3 rounded-lg font-medium shadow-md shadow-blue-500/20 transition-all text-sm cursor-pointer disabled:cursor-not-allowed"
          >
            {isGenerating ? <Clock className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {isGenerating ? 'Synthesizing with Six Agents...' : 'Synthesize SQL'}
          </button>
          
          {/* FINAL RESULT CARD */}
          {finalResult && (
            <div className="border-t border-slate-200 pt-6 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-slate-900 flex items-center gap-2 text-sm">
                  {finalResult.confidence > 0 && finalResult.execution_data?.status !== 'error' ? (
                    <CheckCircle className="w-5 h-5 text-emerald-600" />
                  ) : (
                    <AlertTriangle className="w-5 h-5 text-amber-500" />
                  )}
                  {finalResult.confidence > 0 && finalResult.execution_data?.status !== 'error'
                    ? 'Synthesized SQL Output'
                    : 'Schema Mismatch / Unexecutable'}
                </h3>
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                  finalResult.confidence > 0 && finalResult.execution_data?.status !== 'error'
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-red-100 text-red-800'
                }`}>
                  Confidence: {(finalResult.confidence * 100).toFixed(0)}%
                </span>
              </div>
              
              <div className="bg-slate-950 rounded-lg p-4 relative shadow-inner overflow-hidden">
                <pre className="text-emerald-400 font-mono text-xs overflow-x-auto whitespace-pre-wrap leading-relaxed">
                  <code>{finalResult.sql || '-- No SQL Generated'}</code>
                </pre>
              </div>

              {finalResult.answer && (finalResult.confidence === 0 || finalResult.execution_data?.status === 'error' || finalResult.answer.includes('Schema Error') || finalResult.answer.includes('Failure')) && (
                <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 flex items-start gap-2.5">
                  <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Schema & Repair Diagnostic</span>
                    <p className="mt-0.5 leading-relaxed">{finalResult.answer}</p>
                  </div>
                </div>
              )}

              {/* RISK HEDGING SUMMARY CARD */}
              {finalResult.risk_evaluation && (
                <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-2">
                  <div className="flex items-center justify-between font-semibold text-slate-800">
                    <span className="flex items-center gap-1.5 text-blue-700">
                      <Shield className="w-4 h-4" />
                      Risk Hedging Decision
                    </span>
                    <span className="text-[11px] bg-blue-100 text-blue-800 px-2 py-0.5 rounded font-mono font-medium">
                      Selected: {finalResult.risk_evaluation.selected_candidate_type}
                    </span>
                  </div>
                  <p className="text-slate-600 leading-normal">
                    {finalResult.risk_evaluation.decision_rationale}
                  </p>
                  {finalResult.risk_evaluation.risk_factors && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {finalResult.risk_evaluation.risk_factors.map((f: string, i: number) => (
                        <span key={i} className="text-[10px] bg-white border border-slate-200 text-slate-600 px-2 py-0.5 rounded font-mono">
                          {f}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* EXECUTION RESULT TABLE */}
              {finalResult.execution_data && finalResult.execution_data.status === "success" && finalResult.execution_data.data && (
                <div className="border border-slate-200 rounded-lg overflow-hidden text-xs">
                  <div className="bg-slate-50 px-3.5 py-2 border-b border-slate-200 font-medium text-slate-700 flex justify-between items-center">
                    <span>Database Execution Results</span>
                    <span className="text-[11px] text-slate-500 font-mono">{finalResult.execution_data.rows} rows returned</span>
                  </div>
                  <div className="overflow-x-auto max-h-56">
                    <table className="min-w-full divide-y divide-slate-200">
                      <thead className="bg-slate-100/70 sticky top-0">
                        <tr>
                          {finalResult.execution_data.columns && finalResult.execution_data.columns.map((col, i) => (
                            <th key={i} className="px-3 py-1.5 text-left font-semibold text-slate-600 tracking-wider text-[11px]">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-slate-100 font-mono text-[11px]">
                        {finalResult.execution_data.data.map((row, i) => (
                          <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                            {row.map((cell, j) => (
                              <td key={j} className="px-3 py-1.5 whitespace-nowrap text-slate-700">
                                {cell !== null ? String(cell) : 'NULL'}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {finalResult.execution_data && finalResult.execution_data.status === "error" && (
                <div className="bg-red-50 border border-red-200 text-red-800 p-3.5 rounded-lg text-xs flex gap-2.5 items-start">
                  <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Execution Failure</span>
                    <p className="mt-0.5 text-red-700 font-mono">{finalResult.execution_data.error}</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* RIGHT PANEL: Six Agents Pipeline & Execution Trace */}
        <div className="w-3/5 bg-slate-50/60 p-6 overflow-y-auto flex flex-col gap-6">
          {/* SIX AGENTS PIPELINE OVERVIEW */}
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-blue-600" />
              The Six Intelligent Agents
            </h2>
            <div className="grid grid-cols-3 gap-3">
              {SIX_AGENTS.map((agent, idx) => {
                const Icon = agent.icon;
                const status = getAgentStatus(agent.id);
                return (
                  <div 
                    key={agent.id}
                    className={`p-3 rounded-lg border transition-all ${
                      status === 'completed' 
                        ? 'bg-emerald-50/70 border-emerald-300 shadow-sm' 
                        : status === 'objection'
                        ? 'bg-amber-50/70 border-amber-300 shadow-sm'
                        : status === 'active'
                        ? 'bg-blue-50 border-blue-400 ring-2 ring-blue-400/20'
                        : 'bg-slate-50/80 border-slate-200 opacity-60'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-bold w-4 h-4 rounded-full bg-slate-800 text-white flex items-center justify-center">
                          {idx + 1}
                        </span>
                        <Icon className="w-3.5 h-3.5 text-slate-500" />
                        <span className="font-bold text-xs text-slate-800">{agent.name}</span>
                      </div>
                      {status === 'completed' && <Check className="w-4 h-4 text-emerald-600" />}
                      {status === 'objection' && <AlertTriangle className="w-4 h-4 text-amber-600" />}
                      {status === 'active' && <Clock className="w-4 h-4 text-blue-600 animate-spin" />}
                    </div>
                    <p className="text-[10px] text-slate-500 leading-tight">{agent.desc}</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* AGENT TRACE TIMELINE */}
          <div className="space-y-4">
            <h2 className="text-sm font-bold text-slate-800 flex items-center justify-between sticky top-0 bg-slate-50/90 backdrop-blur-sm py-1 z-10">
              <span>Dynamic Multi-Agent Trace</span>
              <span className="text-xs font-normal text-slate-500">
                {events.length > 0 ? `${Math.min(currentEventIndex + 1, events.length)} of ${events.length} events` : '0 events'}
              </span>
            </h2>

            {events.length === 0 && !isGenerating && (
              <div className="text-center text-slate-400 py-16 bg-white rounded-xl border border-dashed border-slate-200">
                <Database className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">Submit a query to inspect live six-agent reasoning.</p>
              </div>
            )}

            {events.slice(0, currentEventIndex + 1).map((ev, idx) => (
              <div 
                key={idx} 
                className={`p-4 rounded-xl shadow-sm border border-slate-200 transition-all duration-300 relative ${getEventStyle(ev.message_type)}`}
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    {getEventIcon(ev.message_type)}
                    <span className="font-bold text-slate-900 text-xs tracking-wide">
                      {ev.agent}
                    </span>
                    {ev.capability && (
                      <span className="text-[10px] font-semibold bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded-full border border-indigo-200">
                        {ev.capability}
                      </span>
                    )}
                    {ev.target_agents && ev.target_agents.length > 0 && (
                      <span className="text-[10px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                        → {ev.target_agents.join(', ')}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-600">
                    {ev.message_type}
                  </span>
                </div>
                
                <div className="ml-7 space-y-2">
                  <p className="text-slate-800 text-xs leading-relaxed font-medium">
                    {ev.claim}
                  </p>
                  
                  {ev.confidence > 0 && (
                    <div className="flex items-center gap-2 pt-1">
                      <div className="w-36 bg-slate-200 rounded-full h-1.5 overflow-hidden">
                        <div 
                          className="bg-blue-600 h-1.5 rounded-full transition-all duration-500" 
                          style={{ width: `${ev.confidence * 100}%` }}
                        ></div>
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono">
                        Conf: {(ev.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isGenerating && (
              <div className="p-4 flex items-center justify-center text-slate-500 gap-2 animate-pulse bg-white rounded-xl border border-slate-200">
                <Clock className="w-4 h-4 text-blue-600 animate-spin" />
                <span className="text-xs font-medium">Coordinating agent decisions...</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;

