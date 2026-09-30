import React from 'react'

// Renders Text-to-SQL++ result rows as a table.
export default function RowsTable({ rows }) {
  if (!rows || rows.length === 0) return null
  const cols = Array.from(rows.reduce((set, r) => {
    Object.keys(r).forEach((k) => set.add(k))
    return set
  }, new Set()))
  return (
    <div className="rows">
      <table>
        <thead>
          <tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c}>{typeof r[c] === 'object' ? JSON.stringify(r[c]) : String(r[c] ?? '')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
