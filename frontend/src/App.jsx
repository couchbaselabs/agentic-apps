import React, { useState, useRef, useEffect } from 'react'
import Citation from './components/Citation.jsx'
import Steps from './components/Steps.jsx'
import RowsTable from './components/RowsTable.jsx'

const EXAMPLES = [
  'Were any of the following clinical findings observed in study T123456-2: piloerection, ataxia, eyes partially closed, and loose faeces?',
  'Give me 50 example studies done on RAT',
  'What is the lowest NOAEL recorded for BAY-45-A and in which study?',
  'Did BAY-45-A cause any cardiovascular effects in dogs?',
]

// Render an answer string, turning [cite:ID] / [study:ID] markers into hover chips.
function renderAnswer(text, citations) {
  const byId = {}
  citations.forEach((c) => {
    if (c.chunk_id) byId[c.chunk_id] = c
    if (c.study_id) byId['study:' + c.study_id] = c
  })
  const parts = []
  const re = /\[(cite|study):([^\]]+)\]/g
  let last = 0, m, n = 0
  while ((m = re.exec(text)) !== null) {
    parts.push(text.slice(last, m.index))
    const key = m[1] === 'study' ? 'study:' + m[2] : m[2]
    parts.push(<Citation key={n++} c={byId[key] || { chunk_id: m[2] }} idx={n} />)
    last = re.lastIndex
  }
  parts.push(text.slice(last))
  return parts
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [steps, setSteps] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy])

  async function ask(q) {
    if (!q.trim() || busy) return
    setMessages((m) => [...m, { role: 'user', text: q }])
    setInput('')
    setBusy(true)
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, session_id: sessionId }),
      })
      const data = await res.json()
      setSessionId(data.session_id)
      setSteps(data.steps || [])
      setMessages((m) => [...m, { role: 'bot', ...data }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'bot', answer: 'Error: ' + e.message }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <header>
        <span style={{ fontSize: 20 }}>🧬</span>
        <div>
          <h1>PRINCE — Preclinical Information Center</h1>
          <div className="sub">Agentic RAG + Text-to-SQL++ · every store is Couchbase</div>
        </div>
        <span className="badge" style={{ marginLeft: 'auto' }}>Couchbase: FTS + Vector + SQL++</span>
      </header>

      <div className="chat">
        <div className="messages">
          {messages.length === 0 && (
            <div className="msg bot">
              <div className="role">PRINCE</div>
              <div className="bubble">
                Ask about the preclinical safety corpus. I run a five-stage agentic
                workflow (clarify → plan → research → reflect → write). Structured
                questions go through Text-to-SQL++ over Couchbase; findings questions
                go through hybrid vector + keyword search. Every claim is cited.
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={'msg ' + m.role}>
              <div className="role">{m.role === 'user' ? 'You' : 'PRINCE'}</div>
              <div className={'bubble' + (m.needs_clarification ? ' clarify' : '')}>
                {m.role === 'user' && m.text}
                {m.role === 'bot' && m.needs_clarification && (
                  <><strong>Clarifying question:</strong> {m.clarify_question}</>
                )}
                {m.role === 'bot' && !m.needs_clarification && (
                  <>
                    {renderAnswer(m.answer || '', m.citations || [])}
                    {m.sql && <div className="sql" style={{ marginTop: 10 }}>SQL++ ▸ {m.sql}</div>}
                    {m.rows && m.rows.length > 0 && <RowsTable rows={m.rows} />}
                  </>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="spin">PRINCE is researching… (clarify → plan → research → reflect → write)</div>}
          <div ref={endRef} />
        </div>

        <div className="examples">
          {EXAMPLES.map((e, i) => (
            <span key={i} className="chip" onClick={() => ask(e)}>{e.slice(0, 46)}…</span>
          ))}
        </div>

        <div className="composer">
          <input
            value={input}
            placeholder="Ask about a study, compound, finding, NOAEL…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && ask(input)}
          />
          <button disabled={busy} onClick={() => ask(input)}>Ask</button>
        </div>
      </div>

      <div className="side">
        <h2>Intermediate steps</h2>
        <Steps steps={steps} />
      </div>
    </div>
  )
}
