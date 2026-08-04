import React from 'react'

// Renders the workflow's intermediate steps (transparency panel): keyword
// extraction, metadata filter, query expansion, hybrid search, rerank, SQL++, etc.
export default function Steps({ steps }) {
  if (!steps || steps.length === 0) {
    return <div className="spin">Run a query to see the agent's steps.</div>
  }
  return (
    <div>
      {steps.map((s, i) => {
        const { step, ...rest } = s
        return (
          <div className="step" key={i}>
            <span className="k">{step}</span>
            <pre>{JSON.stringify(rest, null, 1)}</pre>
          </div>
        )
      })}
    </div>
  )
}
