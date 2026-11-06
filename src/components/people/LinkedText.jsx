import { useMemo } from 'react'
import { usePeople } from '../../context/PeopleContext'

// Renders text with every recognised person's name turned into a clickable
// link that opens their profile panel. `people` comes from
// GET /api/articles/<id>/people; each person carries `link_forms`, the
// exact strings that refer to them in this article ("Hakainde Hichilema",
// "President Hichilema", "HH" ...). All forms of one person open the same
// profile. Only the names are wrapped; the rest of the text is untouched,
// so the article keeps its formatting.

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

export function buildMatcher(people) {
  const byForm = new Map()
  for (const p of people || []) {
    for (const f of p.link_forms || []) {
      if (f && f.length >= 2 && !byForm.has(f)) byForm.set(f, p)
    }
  }
  if (!byForm.size) return null
  const forms = [...byForm.keys()].sort((a, b) => b.length - a.length)
  // Whole words only: "HH" must not match inside "HHS", "Banda" not inside "Bandas".
  const re = new RegExp(`(?<![\\p{L}\\p{N}_-])(${forms.map(escapeRe).join('|')})(?![\\p{L}\\p{N}_-])`, 'gu')
  return { re, byForm }
}

export default function LinkedText({ text, people, matcher: given }) {
  const matcher = useMemo(() => given ?? buildMatcher(people), [given, people])
  if (!text) return null
  if (!matcher) return text

  const parts = []
  let last = 0
  matcher.re.lastIndex = 0
  for (const m of text.matchAll(matcher.re)) {
    const person = matcher.byForm.get(m[1])
    if (!person) continue
    if (m.index > last) parts.push(text.slice(last, m.index))
    parts.push(<PersonLink key={`${m.index}-${person.id}`} person={person} label={m[1]} />)
    last = m.index + m[1].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <>{parts}</>
}

export function PersonLink({ person, label, className = '' }) {
  const { openPerson, openId } = usePeople()
  const hint = person.headline_position || person.short_description
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        openPerson(person)
      }}
      className={`inline p-0 m-0 bg-transparent border-0 font-[inherit] text-[inherit] leading-[inherit] cursor-pointer
        underline decoration-dotted decoration-indigo-400 underline-offset-[3px] decoration-[1.5px]
        hover:text-indigo-700 hover:decoration-solid focus-visible:outline-2 focus-visible:outline-indigo-500 rounded-sm
        ${openId === person.id ? 'text-indigo-700 decoration-solid' : ''} ${className}`}
      title={hint ? `${person.name} — ${hint}` : `About ${person.name}`}
      aria-label={`${label}: open profile of ${person.name}`}
      aria-haspopup="dialog"
    >
      {label}
    </button>
  )
}
