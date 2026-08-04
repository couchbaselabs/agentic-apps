import React from 'react'

// A hoverable inline citation chip: shows study, page, section, and exact quote —
// the granular per-sentence citation from the article.
export default function Citation({ c, idx }) {
  const label = c.study_id ? c.study_id : (c.chunk_id || '?')
  return (
    <span className="cite">[{idx}]
      <span className="tip">
        <div className="meta">
          {c.study_id && <span>Study {c.study_id} </span>}
          {c.page != null && <span>· p.{c.page} </span>}
          {c.parent_section && <span>· {c.parent_section}</span>}
        </div>
        {c.quote ? c.quote : (c.chunk_id ? `chunk ${c.chunk_id}` : 'source')}
      </span>
    </span>
  )
}
