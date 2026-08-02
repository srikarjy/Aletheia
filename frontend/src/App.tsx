import React, { useState, useCallback } from 'react'
import { 
  Send, Loader2, BookOpen, Scale, 
  ChevronDown, ChevronUp, Copy, Check,
  AlertCircle, CheckCircle, XCircle,
  Search, Brain, GitBranch
} from 'lucide-react'

const API_BASE = ''

interface DebateResponse {
  debate_id: string
  claim: string
  conclusion: string
  verdict: 'supported' | 'refuted' | 'unresolved'
  confidence: number
  confidence_rationale: string
  driving_provenance_ids: number[]
  transcript: TranscriptEntry[]
  sources: Source[]
}

interface TranscriptEntry {
  agent: string
  action: string
  detail: Record<string, unknown>
  source_paper_id: string | null
}

interface Source {
  paper_id: string
  title: string
  used_by: string[]
}

const EXAMPLE_CLAIMS = [
  "BRCA1 mutations increase pancreatic cancer risk",
  "Vitamin D supplementation prevents severe COVID-19 outcomes",
  "Low-dose aspirin reduces all-cause mortality in healthy older adults",
  "Omega-3 fatty acid supplementation reduces major adverse cardiovascular events",
  "Menopausal hormone therapy reduces all-cause mortality in women under 60",
]

function ConfidenceBar({ confidence, verdict }: { confidence: number; verdict: string }) {
  const getColor = () => {
    if (verdict === 'supported') return 'var(--success)'
    if (verdict === 'refuted') return 'var(--danger)'
    return 'var(--warning)'
  }
  return (
    <div className="confidence-bar" style={{ marginTop: '0.5rem' }}>
      <div 
        className="confidence-bar-fill" 
        style={{ 
          width: `${confidence * 100}%`, 
          background: getColor() 
        }} 
      />
    </div>
  )
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const labels = { supported: 'Supported', refuted: 'Refuted', unresolved: 'Unresolved' }
  const classes = { supported: 'badge-supported', refuted: 'badge-refuted', unresolved: 'badge-unresolved' }
  return (
    <span className={`badge ${classes[verdict as keyof typeof classes]}`}>
      {labels[verdict as keyof typeof labels]}
    </span>
  )
}

function ProvenanceRow({ row }: { row: TranscriptEntry & { id?: number } }) {
  const icons = {
    advocate: <Brain className="w-4 h-4" style={{ color: 'var(--accent)' }} />,
    skeptic: <Scale className="w-4 h-4" style={{ color: 'var(--warning)' }} />,
    synthesizer: <CheckCircle className="w-4 h-4" style={{ color: 'var(--success)' }} />,
  }
  
  return (
    <div className={`provenance-row ${row.agent}`}>
      <div className="provenance-header">
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
          {icons[row.agent as keyof typeof icons] || null}
          <strong>{row.agent}</strong>
        </span>
        <span><code>{row.action}</code></span>
        {row.source_paper_id && <span>PMID: <code>{row.source_paper_id}</code></span>}
        {row.id !== undefined && <span>id: <code>{row.id}</code></span>}
      </div>
      <div className="provenance-detail">
        {JSON.stringify(row.detail, null, 2)}
      </div>
    </div>
  )
}

function SourceCard({ source }: { source: Source }) {
  return (
    <div className="source-card">
      <div className="source-title">{source.title}</div>
      <div className="source-meta">
        PMID: <code>{source.paper_id}</code> • Used by: {source.used_by.join(', ')}
      </div>
    </div>
  )
}

function CollapsibleSection({ 
  title, 
  children, 
  icon: Icon, 
  defaultOpen = false,
  count
}: { 
  title: string
  children: React.ReactNode
  icon: React.ReactNode
  defaultOpen?: boolean
  count?: number
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <button 
        onClick={() => setOpen(!open)}
        className="btn btn-ghost"
        style={{ width: '100%', justifyContent: 'space-between', padding: '0.75rem 0' }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {icon}
          <span>{title}</span>
          {count !== undefined && <span className="badge" style={{ background: 'var(--bg)', color: 'var(--fg-muted)' }}>{count}</span>}
        </span>
        {open ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
      </button>
      {open && <div style={{ marginTop: '0.5rem' }}>{children}</div>}
    </div>
  )
}

function Toast({ message, type = 'info', onClose }: { message: string; type?: 'info' | 'success' | 'error'; onClose: () => void }) {
  const icons = { info: AlertCircle, success: CheckCircle, error: XCircle }
  const colors = { info: 'var(--accent)', success: 'var(--success)', error: 'var(--danger)' }
  const Icon = icons[type]
  return (
    <div className="toast" style={{ borderLeft: `4px solid ${colors[type]}` }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
        <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: colors[type] }} />
        <span style={{ flex: 1 }}>{message}</span>
        <button onClick={onClose} className="btn btn-ghost" style={{ padding: '0.25rem' }}>
          <XCircle className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

export default function App() {
  const [claim, setClaim] = useState('')
  const [result, setResult] = useState<DebateResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<{ message: string; type: 'info' | 'success' | 'error' } | null>(null)

  const showToast = useCallback((message: string, type: 'info' | 'success' | 'error' = 'info') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 5000)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!claim.trim()) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(`${API_BASE}/debate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claim: claim.trim() }),
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${response.status}`)
      }

      const data = await response.json()
      setResult(data)
      showToast('Debate completed successfully', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      setError(message)
      showToast(message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    showToast(`${label} copied to clipboard`, 'success')
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{ 
        padding: '1.5rem 2rem', 
        borderBottom: '1px solid var(--border)',
        background: 'rgba(10, 15, 26, 0.9)',
        backdropFilter: 'blur(10px)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '2rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <GitBranch className="w-8 h-8" style={{ color: 'var(--accent)' }} />
            <div>
              <h1 style={{ fontSize: '1.5rem', fontWeight: 700, letterSpacing: '-0.02em' }}>Aletheia</h1>
              <p style={{ fontSize: '0.75rem', color: 'var(--fg-muted)', fontWeight: 500 }}>Multi-Agent Scientific Reasoning</p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <a href="https://github.com/srikarjy/aletheia" target="_blank" rel="noopener noreferrer" className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
              <Search className="w-4 h-4" /> View Source
            </a>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main style={{ flex: 1, padding: '2rem', maxWidth: '1200px', margin: '0 auto', width: '100%' }}>
        {/* Input Section */}
        <section className="card" style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Brain className="w-5 h-5" style={{ color: 'var(--accent)' }} />
            Enter a Scientific Claim
          </h2>
          
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div style={{ flex: 1, minWidth: '300px' }}>
                <textarea
                  className="input"
                  rows={3}
                  value={claim}
                  onChange={(e) => setClaim(e.target.value)}
                  placeholder="e.g., BRCA1 mutations increase pancreatic cancer risk"
                  disabled={loading}
                  style={{ resize: 'vertical', fontFamily: 'inherit' }}
                />
              </div>
              <button 
                type="submit" 
                className="btn btn-primary"
                disabled={loading || !claim.trim()}
                style={{ height: 'fit-content', minWidth: '160px' }}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 loading-spinner" />
                    Running Debate...
                  </>
                ) : (
                  <>
                    <Send className="w-5 h-5" />
                    Start Debate
                  </>
                )}
              </button>
            </div>
            
            {error && (
              <div style={{ marginTop: '1rem', padding: '0.75rem', background: 'rgba(248, 113, 113, 0.1)', border: '1px solid var(--danger)', borderRadius: '6px', color: 'var(--danger)', fontSize: '0.875rem' }}>
                {error}
              </div>
            )}
          </form>

          {/* Example Claims */}
          <div style={{ marginTop: '1.5rem' }}>
            <p style={{ fontSize: '0.875rem', color: 'var(--fg-muted)', marginBottom: '0.75rem' }}>Try one of these curated claims:</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {EXAMPLE_CLAIMS.map((c, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setClaim(c)}
                  disabled={loading}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.75rem', padding: '0.375rem 0.75rem' }}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Results Section */}
        {result && (
          <section style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Verdict Header */}
            <div className="card" style={{ 
              borderColor: result.verdict === 'supported' ? 'var(--success)' : 
                           result.verdict === 'refuted' ? 'var(--danger)' : 'var(--warning)',
              background: `linear-gradient(135deg, var(--card) 0%, ${result.verdict === 'supported' ? 'rgba(74, 222, 128, 0.05)' : result.verdict === 'refuted' ? 'rgba(248, 113, 113, 0.05)' : 'rgba(251, 191, 36, 0.05)'} 100%)`
            }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ flex: 1, minWidth: '280px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                    <VerdictBadge verdict={result.verdict} />
                    <span style={{ fontSize: '0.875rem', color: 'var(--fg-muted)' }}>
                      Debate ID: <code>{result.debate_id.slice(0, 8)}...</code>
                    </span>
                    <button 
                      className="btn btn-ghost" 
                      onClick={() => copyToClipboard(result.debate_id, 'Debate ID')}
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                    >
                      <Copy className="w-3 h-3" />
                    </button>
                  </div>
                  <p style={{ fontSize: '1rem', color: 'var(--fg-muted)' }}>
                    <strong>Claim:</strong> {result.claim}
                  </p>
                </div>
                <div style={{ textAlign: 'right', minWidth: '180px' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--fg-muted)', marginBottom: '0.25rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Confidence</div>
                  <div style={{ fontSize: '3rem', fontWeight: 700, fontFamily: "'IBM Plex Mono', monospace", color: result.verdict === 'supported' ? 'var(--success)' : result.verdict === 'refuted' ? 'var(--danger)' : 'var(--warning)' }}>
                    {(result.confidence * 100).toFixed(0)}%
                  </div>
                  <ConfidenceBar confidence={result.confidence} verdict={result.verdict} />
                </div>
              </div>
            </div>

            {/* Conclusion */}
            <div className="card">
              <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <BookOpen className="w-5 h-5" style={{ color: 'var(--accent)' }} />
                Synthesized Conclusion
              </h3>
              <div style={{ 
                whiteSpace: 'pre-wrap', 
                lineHeight: 1.8,
                padding: '1rem',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                position: 'relative',
              }}>
                {result.conclusion}
                <button 
                  className="btn btn-ghost"
                  onClick={() => copyToClipboard(result.conclusion, 'Conclusion')}
                  style={{ position: 'absolute', top: '0.5rem', right: '0.5rem', padding: '0.25rem' }}
                >
                  <Copy className="w-4 h-4" />
                </button>
              </div>
              <div style={{ marginTop: '1rem', padding: '1rem', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '0.875rem' }}>
                <strong>Confidence Rationale:</strong>
                <p style={{ marginTop: '0.5rem', color: 'var(--fg-muted)' }}>{result.confidence_rationale}</p>
                <p style={{ marginTop: '0.5rem' }}>
                  <strong>Driving Provenance IDs:</strong>{' '}
                  <code>{result.driving_provenance_ids.join(', ')}</code>
                </p>
              </div>
            </div>

            {/* Sources */}
            <CollapsibleSection 
              title="Sources" 
              icon={<BookOpen className="w-5 h-5" />}
              count={result.sources.length}
              defaultOpen={true}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {result.sources.map((source, i) => (
                  <SourceCard key={i} source={source} />
                ))}
              </div>
            </CollapsibleSection>

            {/* Transcript */}
            <CollapsibleSection 
              title="Full Debate Transcript (Provenance)" 
              icon={<GitBranch className="w-5 h-5" />}
              count={result.transcript.length}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {result.transcript.map((row, i) => (
                  <ProvenanceRow key={i} row={{ ...row, id: i + 1 }} />
                ))}
              </div>
            </CollapsibleSection>

            {/* Raw JSON */}
            <CollapsibleSection 
              title="Raw JSON Response" 
              icon={<Search className="w-5 h-5" />}
            >
              <pre className="scrollbar-thin">
                {JSON.stringify(result, null, 2)}
                <button 
                  className="btn btn-ghost"
                  onClick={() => copyToClipboard(JSON.stringify(result, null, 2), 'JSON')}
                  style={{ marginTop: '1rem' }}
                >
                  <Copy className="w-4 h-3" /> Copy JSON
                </button>
              </pre>
            </CollapsibleSection>
          </section>
        )}

        {/* Empty State */}
        {!result && !loading && !error && (
          <div className="card" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
            <Brain className="w-16 h-16 mx-auto" style={{ color: 'var(--accent)', opacity: 0.5, marginBottom: '1.5rem' }} />
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>Ready to debate</h2>
            <p style={{ color: 'var(--fg-muted)', marginBottom: '1.5rem', maxWidth: '400px', margin: '0 auto 1.5rem' }}>
              Enter a scientific claim above. Aletheia will retrieve real PubMed evidence, 
              run a multi-agent debate (Advocate → Skeptic → Synthesizer), and return 
              a structured conclusion with full provenance traceability.
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              {EXAMPLE_CLAIMS.slice(0, 3).map((c, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setClaim(c)}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.75rem', padding: '0.5rem 1rem' }}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer style={{ 
        padding: '1.5rem 2rem', 
        borderTop: '1px solid var(--border)',
        background: 'rgba(10, 15, 26, 0.9)',
      }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', fontSize: '0.75rem', color: 'var(--fg-muted)' }}>
          <span>Aletheia — Built for scientific AI you can actually trust</span>
          <div style={{ display: 'flex', gap: '1.5rem' }}>
            <span>Phase 0-4 Complete</span>
            <span>5-Claim Eval Set Ready</span>
            <span>Eval Harness Implemented</span>
          </div>
        </div>
      </footer>

      {toast && (
        <Toast 
          message={toast.message} 
          type={toast.type} 
          onClose={() => setToast(null)} 
        />
      )}
    </div>
  )
}