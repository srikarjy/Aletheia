import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, Archive, ArrowRight, BookOpen, Brain, Check, ChevronDown,
  Clipboard, Database, FlaskConical, Gauge, GitBranch, Layers3, Loader2,
  RefreshCw, Scale, Search, Server, ShieldCheck, Sparkles, Trash2, X,
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL ?? ''
type Verdict = 'supported' | 'refuted' | 'unresolved'
type View = 'workspace' | 'memory' | 'system'
type ResultTab = 'evidence' | 'reasoning' | 'json'

interface SignalBreakdown { literature: number; protein_evidence: number; clinical_evidence: number; llm_rating: number }
interface TranscriptEntry { agent: string; action: string; detail: Record<string, unknown>; source_paper_id: string | null }
interface Source { paper_id: string; title: string; used_by: string[]; retracted?: boolean; concern?: boolean; retraction_notice?: string | null }
interface DebateResponse {
  debate_id: string; claim: string; conclusion: string; verdict: Verdict; confidence: number
  confidence_rationale: string; signal_breakdown?: SignalBreakdown | null
  driving_provenance_ids: number[]; transcript: TranscriptEntry[]; sources: Source[]
}
interface JobResponse { job_id: string; status: 'pending' | 'running' | 'completed' | 'failed'; result: DebateResponse | null; error?: string | null; cache_hit?: boolean }
interface MemoryItem { debate_id: string; claim: string; verdict: Verdict; confidence: number; pipeline: string; from_cache: boolean; created_at: number }
interface HealthResponse {
  status: string; version: string; cache_stats: { claims: number; embeddings: number; jobs: number }
  infrastructure?: { api: string; persistence: string; cache: string; queue: string; llm?: { provider: string; model: string } }
}

const EXAMPLES = [
  'BRCA1 mutations increase pancreatic cancer risk',
  'Vitamin D supplementation prevents severe COVID-19 outcomes',
  'Low-dose aspirin reduces all-cause mortality in healthy older adults',
]
const signalLabels: Record<keyof SignalBreakdown, string> = {
  literature: 'Literature', protein_evidence: 'Protein evidence', clinical_evidence: 'Clinical evidence', llm_rating: 'Rubric rating',
}
const wait = (milliseconds: number) => new Promise(resolve => setTimeout(resolve, milliseconds))

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

function Mark() { return <div className="mark" aria-hidden="true"><span /><span /><span /></div> }
function VerdictBadge({ verdict }: { verdict: Verdict }) { return <span className={`verdict verdict-${verdict}`}>{verdict}</span> }
function formatDate(value: number) { return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value * 1000)) }
function sourceUrl(source: Source) { return source.paper_id.startsWith('NCT') ? `https://clinicaltrials.gov/study/${source.paper_id}` : `https://pubmed.ncbi.nlm.nih.gov/${source.paper_id}/` }

export default function App() {
  const [view, setView] = useState<View>('workspace')
  const [claim, setClaim] = useState('')
  const [multiAgent, setMultiAgent] = useState(false)
  const [result, setResult] = useState<DebateResponse | null>(null)
  const [resultTab, setResultTab] = useState<ResultTab>('evidence')
  const [loading, setLoading] = useState(false)
  const [jobStatus, setJobStatus] = useState('Ready')
  const [error, setError] = useState<string | null>(null)
  const [memory, setMemory] = useState<MemoryItem[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [copied, setCopied] = useState(false)

  const loadMemory = useCallback(async () => {
    try { setMemory((await api<{ items: MemoryItem[] }>('/memory/research?limit=30')).items) } catch { /* graceful local-only mode */ }
  }, [])
  const loadHealth = useCallback(async () => { try { setHealth(await api<HealthResponse>('/health')) } catch { setHealth(null) } }, [])
  useEffect(() => { void loadMemory(); void loadHealth() }, [loadMemory, loadHealth])

  const runClaim = async (event: FormEvent) => {
    event.preventDefault()
    if (!claim.trim() || loading) return
    setLoading(true); setError(null); setResult(null); setJobStatus('Submitting')
    try {
      let job = await api<JobResponse>('/debate/async', { method: 'POST', body: JSON.stringify({ claim: claim.trim(), multi_agent: multiAgent }) })
      let attempts = 0
      while (!job.result && job.status !== 'failed' && attempts < 240) {
        setJobStatus(job.status === 'running' ? 'Reasoning over evidence' : 'Queued')
        await wait(1250)
        job = await api<JobResponse>(`/debate/jobs/${job.job_id}`)
        attempts += 1
      }
      if (job.status === 'failed') throw new Error(job.error || 'The analysis failed')
      if (!job.result) throw new Error('The analysis took too long. It will remain available when complete.')
      setResult(job.result); setJobStatus(job.cache_hit ? 'Restored from cache' : 'Analysis complete'); setResultTab('evidence')
      await Promise.all([loadMemory(), loadHealth()])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to run this analysis'); setJobStatus('Needs attention')
    } finally { setLoading(false) }
  }

  const openMemory = async (item: MemoryItem) => {
    setError(null)
    try {
      setResult(await api<DebateResponse>(`/memory/research/${item.debate_id}`)); setClaim(item.claim)
      setView('workspace'); setResultTab('evidence'); setJobStatus('Restored from research memory')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to open this analysis') }
  }
  const removeMemory = async (event: React.MouseEvent, item: MemoryItem) => {
    event.stopPropagation(); await api(`/memory/research/${item.debate_id}`, { method: 'DELETE' }); setMemory(current => current.filter(entry => entry.debate_id !== item.debate_id))
  }
  const copyConclusion = async () => {
    if (!result) return
    await navigator.clipboard.writeText(result.conclusion); setCopied(true); setTimeout(() => setCopied(false), 1600)
  }
  const progress = useMemo(() => !loading ? (result ? 100 : 0) : jobStatus === 'Submitting' ? 12 : jobStatus === 'Queued' ? 30 : multiAgent ? 62 : 76, [jobStatus, loading, multiAgent, result])

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><Mark /><div><strong>Aletheia</strong><span>evidence engine</span></div></div>
      <nav aria-label="Primary navigation">
        <button className={view === 'workspace' ? 'active' : ''} onClick={() => setView('workspace')}><FlaskConical />Workspace</button>
        <button className={view === 'memory' ? 'active' : ''} onClick={() => { setView('memory'); void loadMemory() }}><Archive />Research memory <span className="nav-count">{memory.length}</span></button>
        <button className={view === 'system' ? 'active' : ''} onClick={() => { setView('system'); void loadHealth() }}><Activity />System</button>
      </nav>
      <div className="sidebar-foot"><div className="status-line"><span className={health ? 'status-dot online' : 'status-dot'} />{health ? 'Services operational' : 'Checking services'}</div><p>Research prototype<br />Not for clinical decisions</p></div>
    </aside>

    <main>
      <header className="topbar"><div><span className="eyebrow">SCIENTIFIC REASONING WORKBENCH</span><h1>{view === 'workspace' ? 'Interrogate a claim' : view === 'memory' ? 'Research memory' : 'System control plane'}</h1></div><div className="runtime-pill"><span className="pulse" /> {jobStatus}</div></header>

      {view === 'workspace' && <div className="workspace">
        <section className="composer-panel">
          <form onSubmit={runClaim}><label htmlFor="claim">Claim to investigate</label><div className="composer"><textarea id="claim" value={claim} onChange={event => setClaim(event.target.value)} disabled={loading} rows={3} placeholder="Enter a concrete scientific or medical claim…" /><button className="run-button" disabled={!claim.trim() || loading}>{loading ? <Loader2 className="spin" /> : <ArrowRight />}{loading ? 'Analyzing' : 'Run analysis'}</button></div></form>
          <div className="composer-options">
            <div className="mode-picker" aria-label="Reasoning mode">
              <button className={!multiAgent ? 'selected' : ''} onClick={() => setMultiAgent(false)} type="button"><Sparkles /> Evidence synthesis <small>fast · measured default</small></button>
              <button className={multiAgent ? 'selected' : ''} onClick={() => setMultiAgent(true)} type="button"><Scale /> Full agent debate <small>advocate · skeptic · judge</small></button>
            </div>
            <div className="examples"><span>Try</span>{EXAMPLES.map(example => <button key={example} onClick={() => setClaim(example)} type="button">{example}</button>)}</div>
          </div>
          {loading && <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>}
          {error && <div className="error-banner"><X />{error}</div>}
        </section>

        {!result && !loading && <section className="empty-grid">
          <div className="empty-primary"><div className="orbit"><Brain /><i /><i /><i /></div><h2>Evidence first. Every time.</h2><p>Aletheia retrieves scientific sources, makes the reasoning trace inspectable, and saves completed work so it can be reopened.</p></div>
          <div className="loop-card"><span className="eyebrow">THE LOOP</span>{['Retrieve grounded evidence', 'Challenge claims and sources', 'Synthesize with a written rubric', 'Validate and persist provenance'].map((step, index) => <div className="loop-step" key={step}><b>0{index + 1}</b><span>{step}</span>{index < 3 && <i />}</div>)}</div>
        </section>}

        {loading && <section className="working-state"><div className="working-orb"><Brain /><span /></div><span className="eyebrow">ACTIVE JOB</span><h2>{jobStatus}</h2><p>{multiAgent ? 'The advocate, skeptic, and synthesizer are working through the evidence.' : 'Retrieving evidence and applying the confidence rubric.'}</p><div className="working-stages"><span className="done">Retrieve</span><i /><span className={progress > 50 ? 'done' : ''}>Reason</span><i /><span>Validate</span><i /><span>Remember</span></div></section>}
        {result && !loading && <ResultWorkspace result={result} tab={resultTab} setTab={setResultTab} copyConclusion={copyConclusion} copied={copied} />}
      </div>}

      {view === 'memory' && <section className="memory-view">
        <div className="section-heading"><div><span className="eyebrow">PERSISTED IN POSTGRES</span><h2>{memory.length} recent analyses</h2></div><button className="icon-button" onClick={() => void loadMemory()} aria-label="Refresh memory"><RefreshCw /></button></div>
        {memory.length === 0 ? <div className="empty-message"><Archive /><h3>No saved analyses yet</h3><p>Completed work will appear here automatically.</p></div> : <div className="memory-list">{memory.map(item => <button className="memory-row" key={item.debate_id} onClick={() => void openMemory(item)}><div className="memory-icon"><BookOpen /></div><div className="memory-copy"><div><VerdictBadge verdict={item.verdict} /><span>{item.pipeline.replace('_', ' ')}</span>{item.from_cache && <span>cache</span>}</div><strong>{item.claim}</strong><small>{formatDate(item.created_at)} · {Math.round(item.confidence * 100)}% confidence</small></div><ArrowRight className="memory-arrow" /><span className="delete-memory" role="button" tabIndex={0} onClick={event => void removeMemory(event, item)}><Trash2 /></span></button>)}</div>}
      </section>}
      {view === 'system' && <SystemView health={health} refresh={loadHealth} />}
    </main>
  </div>
}

function ResultWorkspace({ result, tab, setTab, copyConclusion, copied }: { result: DebateResponse; tab: ResultTab; setTab: (tab: ResultTab) => void; copyConclusion: () => void; copied: boolean }) {
  const signals = result.signal_breakdown
  return <section className="result-workspace">
    <div className="result-summary"><div className="verdict-score"><VerdictBadge verdict={result.verdict} /><strong>{Math.round(result.confidence * 100)}<small>%</small></strong><span>confidence</span></div><div className="summary-copy"><span className="eyebrow">ASSESSED CLAIM</span><h2>{result.claim}</h2><p>{result.conclusion}</p><button className="text-button" onClick={copyConclusion}>{copied ? <Check /> : <Clipboard />}{copied ? 'Copied' : 'Copy conclusion'}</button></div></div>
    {signals && <div className="signal-grid">{(Object.keys(signalLabels) as (keyof SignalBreakdown)[]).map(key => <div className="signal" key={key}><div><span>{signalLabels[key]}</span><b>{Math.round(signals[key] * 100)}</b></div><div className="signal-track"><i style={{ width: `${signals[key] * 100}%` }} /></div></div>)}</div>}
    <div className="result-tabs" role="tablist"><button className={tab === 'evidence' ? 'active' : ''} onClick={() => setTab('evidence')}><BookOpen />Evidence <span>{result.sources.length}</span></button><button className={tab === 'reasoning' ? 'active' : ''} onClick={() => setTab('reasoning')}><GitBranch />Reasoning trace <span>{result.transcript.length}</span></button><button className={tab === 'json' ? 'active' : ''} onClick={() => setTab('json')}><Search />Raw response</button></div>
    {tab === 'evidence' && <div className="evidence-list">{result.sources.map(source => <a href={sourceUrl(source)} target="_blank" rel="noreferrer" className="evidence-row" key={source.paper_id}><div className="source-index">{source.paper_id.startsWith('NCT') ? 'TRIAL' : 'PMID'}<strong>{source.paper_id}</strong></div><div><h3>{source.title}</h3><p>Used by {source.used_by.join(', ')}</p>{(source.retracted || source.concern) && <span className="source-warning">Integrity notice: {source.retraction_notice || (source.retracted ? 'retracted' : 'expression of concern')}</span>}</div><ArrowRight /></a>)}</div>}
    {tab === 'reasoning' && <div className="trace-layout"><aside><span className="eyebrow">CONFIDENCE RATIONALE</span><p>{result.confidence_rationale}</p><small>Driving provenance: {result.driving_provenance_ids.join(', ') || '—'}</small></aside><div className="trace-list">{result.transcript.map((entry, index) => <TraceEntry entry={entry} index={index} key={`${entry.agent}-${index}`} />)}</div></div>}
    {tab === 'json' && <pre className="json-panel">{JSON.stringify(result, null, 2)}</pre>}
  </section>
}

function TraceEntry({ entry, index }: { entry: TranscriptEntry; index: number }) {
  const [open, setOpen] = useState(false)
  return <button className={`trace-entry agent-${entry.agent}`} onClick={() => setOpen(!open)}><div className="trace-number">{String(index + 1).padStart(2, '0')}</div><div className="trace-copy"><div><strong>{entry.agent.replace('_', ' ')}</strong><span>{entry.action}</span>{entry.source_paper_id && <code>{entry.source_paper_id}</code>}</div>{open && <pre>{JSON.stringify(entry.detail, null, 2)}</pre>}</div><ChevronDown className={open ? 'rotated' : ''} /></button>
}

function SystemView({ health, refresh }: { health: HealthResponse | null; refresh: () => Promise<void> }) {
  const infra = health?.infrastructure
  const cards = [
    { icon: Server, label: 'API', value: infra?.api || 'unavailable', detail: `FastAPI ${health?.version || ''}` },
    { icon: Database, label: 'Memory', value: infra?.persistence || 'checking', detail: 'Research runs + job ledger' },
    { icon: Layers3, label: 'Cache', value: infra?.cache || 'checking', detail: `${health?.cache_stats.claims ?? 0} response · ${health?.cache_stats.embeddings ?? 0} vectors` },
    { icon: Gauge, label: 'LLM gateway', value: infra?.llm ? `${infra.llm.provider} · ${infra.llm.model}` : 'checking', detail: infra?.queue || 'Background execution' },
  ]
  return <section className="system-view"><div className="section-heading"><div><span className="eyebrow">RUNTIME TOPOLOGY</span><h2>Infrastructure health</h2></div><button className="icon-button" onClick={() => void refresh()}><RefreshCw /></button></div><div className="system-grid">{cards.map(({ icon: Icon, label, value, detail }) => <div className="system-card" key={label}><div className="system-icon"><Icon /></div><span>{label}</span><h3>{value}</h3><p>{detail}</p><div className="healthy"><ShieldCheck />operational</div></div>)}</div><div className="architecture-strip"><span className="eyebrow">REQUEST PATH</span><div><b>React workbench</b><ArrowRight /><b>FastAPI orchestration</b><ArrowRight /><b>Provider-neutral agents</b><ArrowRight /><b>Postgres + pgvector</b></div></div></section>
}
