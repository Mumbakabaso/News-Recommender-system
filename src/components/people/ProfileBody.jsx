import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BadgeCheck, AlertTriangle, ExternalLink, Newspaper, BookOpen, Briefcase, Award, Scale, Landmark,
  Activity, User, ChevronDown, Info, Clock, GraduationCap, Flag, MapPin, CalendarDays,
} from 'lucide-react'

// Everything inside a person's profile, shared by the side panel (compact)
// and the full profile page. `data` is GET /api/people/<id>.

export function formatDate(value) {
  if (!value) return ''
  if (/^-?\d{1,4}$/.test(value)) return value // year only
  if (/^\d{4}-\d{2}$/.test(value)) {
    const [y, m] = value.split('-')
    return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  }
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function age(birth, died) {
  if (!birth || died || !/^\d{4}-\d{2}-\d{2}$/.test(birth)) return null
  const b = new Date(birth)
  const now = new Date()
  let a = now.getFullYear() - b.getFullYear()
  if (now < new Date(now.getFullYear(), b.getMonth(), b.getDate())) a -= 1
  return a
}

export function Avatar({ person, size = 'lg' }) {
  const [broken, setBroken] = useState(false)
  const dims = size === 'lg' ? 'w-20 h-20 text-2xl' : size === 'md' ? 'w-14 h-14 text-lg' : 'w-10 h-10 text-sm'
  const initials = (person.name || person.full_name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
  if (person.image_url && !broken) {
    return (
      <img
        src={person.image_url}
        alt={`Photo of ${person.name}`}
        onError={() => setBroken(true)}
        className={`${dims} rounded-full object-cover object-top bg-slate-100 shrink-0 ring-2 ring-white shadow`}
        loading="lazy"
      />
    )
  }
  return (
    <div
      className={`${dims} rounded-full bg-gradient-to-br from-indigo-100 to-slate-200 text-indigo-800 font-semibold
        flex items-center justify-center shrink-0 ring-2 ring-white shadow`}
      aria-hidden="true"
    >
      {initials}
    </div>
  )
}

const STATUS = {
  verified: { label: 'Verified record', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  reported: { label: 'Reported', cls: 'bg-slate-50 text-slate-500 border-slate-200' },
  claimed: { label: 'Claimed', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  disputed: { label: 'Disputed', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
}
const LEGAL = {
  allegation: { label: 'Allegation — not proven', cls: 'bg-amber-50 text-amber-800 border-amber-200' },
  investigation: { label: 'Under investigation', cls: 'bg-amber-50 text-amber-800 border-amber-200' },
  charge: { label: 'Charge — not a conviction', cls: 'bg-orange-50 text-orange-800 border-orange-200' },
  court_finding: { label: 'Court finding', cls: 'bg-sky-50 text-sky-800 border-sky-200' },
  conviction: { label: 'Conviction', cls: 'bg-rose-50 text-rose-800 border-rose-200' },
  acquittal: { label: 'Cleared / charges dropped', cls: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
  public_debate: { label: 'Public debate', cls: 'bg-slate-50 text-slate-600 border-slate-200' },
}

function Pill({ meta }) {
  if (!meta) return null
  return (
    <span className={`inline-block align-middle text-[10.5px] font-medium px-1.5 py-px rounded border ${meta.cls}`}>
      {meta.label}
    </span>
  )
}

const SECTION_ICONS = {
  biography: BookOpen, career: Briefcase, policies: Landmark, achievements: Award, controversies: Scale, current: Activity,
}

function Citations({ ids, numbering }) {
  const nums = (ids || []).map((id) => numbering.get(id)).filter(Boolean)
  if (!nums.length) return null
  return (
    <sup className="ml-0.5 text-[10px] text-indigo-600 font-medium whitespace-nowrap">
      {nums.map((n) => (
        <a key={n} href={`#ref-${n}`} className="hover:underline" onClick={(e) => scrollToRef(e, n)}>
          [{n}]
        </a>
      ))}
    </sup>
  )
}

function scrollToRef(e, n) {
  const el = document.getElementById(`ref-${n}`)
  if (el) {
    e.preventDefault()
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('bg-indigo-50')
    setTimeout(() => el.classList.remove('bg-indigo-50'), 1500)
  }
}

function Section({ id, title, items, numbering, defaultOpen, compact }) {
  const [open, setOpen] = useState(defaultOpen)
  const Icon = SECTION_ICONS[id] || Info
  if (!items?.length) return null
  return (
    <section className="border-t border-slate-100">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 py-3 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <Icon className="w-4 h-4 text-indigo-500" /> {title}
          <span className="text-xs font-normal text-slate-400">({items.length})</span>
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <ul className={`pb-4 space-y-2.5 ${compact ? 'text-[14px]' : 'text-[15px]'} text-slate-700 leading-relaxed`}>
          {items.map((it, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-2 w-1.5 h-1.5 rounded-full bg-slate-300 shrink-0" />
              <span className="min-w-0">
                {it.date && <span className="text-xs font-medium text-slate-500 mr-1.5">{formatDate(it.date)}</span>}
                {it.text}
                <Citations ids={it.source_ids} numbering={numbering} />{' '}
                {id === 'controversies' && <Pill meta={LEGAL[it.legal_status] || LEGAL.public_debate} />}{' '}
                {it.status && it.status !== 'reported' && <Pill meta={STATUS[it.status]} />}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function FactRow({ icon: Icon, label, children }) {
  if (!children) return null
  return (
    <div className="flex gap-2.5 py-1.5">
      <Icon className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wide text-slate-400">{label}</div>
        <div className="text-sm text-slate-800">{children}</div>
      </div>
    </div>
  )
}

function Positions({ positions, compact }) {
  const [showAll, setShowAll] = useState(false)
  if (!positions?.length) return null
  const sorted = [...positions].sort(
    (a, b) => Number(b.is_current) - Number(a.is_current) || (b.start_date || '').localeCompare(a.start_date || ''),
  )
  const shown = showAll ? sorted : sorted.slice(0, compact ? 4 : 8)
  return (
    <div className="mt-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">Positions held</h3>
      <ol className="relative border-l-2 border-slate-100 ml-1.5 space-y-3">
        {shown.map((p) => (
          <li key={p.id} className="pl-4 relative">
            <span
              className={`absolute -left-[7px] top-1.5 w-3 h-3 rounded-full border-2 border-white ${
                p.is_current ? 'bg-emerald-500' : 'bg-slate-300'
              }`}
            />
            <div className="text-sm font-medium text-slate-800">
              {p.title}
              {p.organization && !p.title.toLowerCase().includes(p.organization.toLowerCase()) && (
                <span className="font-normal text-slate-500"> · {p.organization}</span>
              )}
              {p.is_current && (
                <span className="ml-1.5 text-[10.5px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-px rounded">
                  Current
                </span>
              )}
            </div>
            <div className="text-xs text-slate-500">
              {p.start_date ? formatDate(p.start_date) : 'Start date not recorded'} –{' '}
              {p.end_date ? formatDate(p.end_date) : p.is_current ? 'present' : 'end date not recorded'}
              {p.party && <> · {p.party}</>}
            </div>
          </li>
        ))}
      </ol>
      {sorted.length > shown.length && (
        <button onClick={() => setShowAll(true)} className="mt-2 text-xs font-medium text-indigo-600 hover:underline">
          Show all {sorted.length} positions
        </button>
      )}
    </div>
  )
}

export function Developments({ items, compact }) {
  if (!items?.length) {
    return <p className="text-sm text-slate-400">No recent news found yet.</p>
  }
  return (
    <ul className="space-y-3">
      {items.map((d) => {
        const inner = (
          <>
            <div className="text-sm font-medium text-slate-800 group-hover:text-indigo-700 leading-snug">{d.title}</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-500">
              <span className="font-medium text-slate-600">{d.publisher || 'Unknown source'}</span>
              {d.published_at && (
                <span className="inline-flex items-center gap-1">
                  <CalendarDays className="w-3 h-3" />
                  {formatDate(d.published_at)}
                </span>
              )}
              {d.tier <= 4 && (
                <span className="text-[10.5px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 rounded">
                  {d.tier_label}
                </span>
              )}
              {['appointment', 'resignation', 'legal', 'election'].includes(d.kind) && (
                <span className="text-[10.5px] font-semibold text-indigo-700 bg-indigo-50 px-1.5 rounded capitalize">
                  {d.kind}
                </span>
              )}
            </div>
            {!compact && d.summary && <p className="mt-1 text-sm text-slate-600 line-clamp-2">{d.summary}</p>}
          </>
        )
        return (
          <li key={d.id}>
            {d.article_id ? (
              <Link to={`/article/${d.article_id}`} className="group block">
                {inner}
              </Link>
            ) : d.url ? (
              <a href={d.url} target="_blank" rel="noreferrer" className="group block">
                {inner}
                <span className="sr-only">(opens the original source)</span>
              </a>
            ) : (
              <div>{inner}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

export default function ProfileBody({ data, compact = false }) {
  const profile = data.profile || {}
  const sources = data.sources || {}

  // Number the references in the order they are used.
  const numbering = useMemo(() => {
    const m = new Map()
    const add = (ids) => (ids || []).forEach((id) => sources[id] && !m.has(id) && m.set(id, m.size + 1))
    add(profile.summary?.source_ids)
    for (const key of profile.section_order || []) {
      for (const it of profile.sections?.[key] || []) add(it.source_ids)
    }
    for (const d of profile.disagreements || []) add(d.source_ids)
    for (const p of data.positions || []) add(p.source_id ? [p.source_id] : [])
    return m
  }, [profile, sources, data.positions])

  const facts = data.facts || {}
  const education = facts.education?.map((e) => e.value + (e.detail ? ` (${e.detail})` : '')).join('; ')
  const party = facts.party_current?.[0]?.value || facts.party?.find((p) => !p.end_date)?.value
  const died = facts.death_date?.[0]?.value
  const years = age(data.birth_date, died)
  const order = profile.section_order || []
  const titles = profile.section_titles || {}

  return (
    <div>
      {profile.summary?.text && (
        <p className={`${compact ? 'text-[15px]' : 'text-base'} text-slate-700 leading-relaxed`}>
          {profile.summary.text}
          <Citations ids={profile.summary.source_ids} numbering={numbering} />
        </p>
      )}

      {/* A. Basic information */}
      <div className={`mt-4 grid ${compact ? 'grid-cols-1' : 'sm:grid-cols-2'} gap-x-6 bg-slate-50 rounded-xl px-4 py-2`}>
        <FactRow icon={User} label="Full name">{data.full_name !== data.name ? data.full_name : null}</FactRow>
        <FactRow icon={CalendarDays} label="Born">
          {data.birth_date && (
            <>
              {formatDate(data.birth_date)}
              {years !== null && <span className="text-slate-500"> (age {years})</span>}
            </>
          )}
        </FactRow>
        <FactRow icon={MapPin} label="Place of birth">{data.birth_place}</FactRow>
        <FactRow icon={Flag} label="Nationality">{data.nationality}</FactRow>
        <FactRow icon={GraduationCap} label="Education">{education}</FactRow>
        <FactRow icon={Landmark} label="Party">{party}</FactRow>
        <FactRow icon={Briefcase} label="Occupation">
          {facts.occupation?.map((o) => o.value).slice(0, 4).join(', ')}
        </FactRow>
        {died && <FactRow icon={CalendarDays} label="Died">{formatDate(died)}</FactRow>}
      </div>

      <Positions positions={data.positions} compact={compact} />

      {profile.disagreements?.length > 0 && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-amber-800 mb-1">
            <AlertTriangle className="w-4 h-4" /> Sources disagree
          </div>
          <ul className="space-y-1 text-sm text-amber-900">
            {profile.disagreements.map((d, i) => (
              <li key={i}>
                <span className="font-medium">{d.topic}:</span> {d.details}
                <Citations ids={d.source_ids} numbering={numbering} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* B–D. Generated sections; E. Latest developments comes next */}
      <div className="mt-4">
        {order
          .filter((k) => k !== 'current')
          .map((k, i) => (
            <Section
              key={k}
              id={k}
              title={titles[k] || k}
              items={profile.sections?.[k]}
              numbering={numbering}
              defaultOpen={!compact || i < 2}
              compact={compact}
            />
          ))}
      </div>

      <section className="border-t border-slate-100 pt-3 mt-1">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800 mb-3">
          <Newspaper className="w-4 h-4 text-indigo-500" /> Latest developments
          {data.refreshing && <span className="text-xs font-normal text-slate-400">· checking for newer stories…</span>}
        </h3>
        <Developments items={data.developments} compact={compact} />
        {data.updated?.developments_updated_at && (
          <p className="mt-2 text-[11px] text-slate-400 flex items-center gap-1">
            <Clock className="w-3 h-3" /> News checked {formatDate(data.updated.developments_updated_at)}
          </p>
        )}
      </section>

      {profile.notes?.length > 0 && (
        <div className="mt-5 space-y-1.5">
          {profile.notes.map((n, i) => (
            <p key={i} className="flex gap-1.5 text-xs text-slate-500">
              <Info className="w-3.5 h-3.5 shrink-0 mt-px" /> {n}
            </p>
          ))}
        </div>
      )}

      <References numbering={numbering} sources={sources} />

      <p className="mt-4 text-[11px] text-slate-400 leading-relaxed">
        {profile.engine === 'gemini'
          ? 'Written by AI (Google Gemini) only from the sources listed; statements without a source are removed.'
          : profile.engine === 'offline'
            ? 'Compiled automatically from the sources listed (structured records and reference articles).'
            : null}{' '}
        {data.updated?.bio_updated_at && <>Profile updated {formatDate(data.updated.bio_updated_at)}. </>}
        {data.image_source_url && (
          <>
            Photo:{' '}
            <a href={data.image_source_url} target="_blank" rel="noreferrer" className="underline hover:text-slate-600">
              {data.image_credit || 'Wikimedia Commons'}
            </a>
            .
          </>
        )}
      </p>
    </div>
  )
}

function References({ numbering, sources }) {
  const list = [...numbering.entries()].sort((a, b) => a[1] - b[1])
  if (!list.length) return null
  return (
    <section className="mt-5 border-t border-slate-100 pt-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">References</h3>
      <ol className="space-y-1">
        {list.map(([id, n]) => {
          const s = sources[id]
          return (
            <li key={id} id={`ref-${n}`} className="text-xs text-slate-600 rounded transition-colors flex gap-1.5">
              <span className="text-slate-400 w-6 shrink-0 text-right">[{n}]</span>
              <span className="min-w-0">
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer" className="hover:text-indigo-600 hover:underline">
                    {s.title || s.url}
                  </a>
                ) : (
                  s.title
                )}
                <span className="text-slate-400">
                  {' '}
                  — {s.publisher || s.domain}
                  {s.published_at && <>, {formatDate(s.published_at)}</>}
                  {s.tier <= 4 && (
                    <span className="inline-flex items-center gap-0.5 ml-1 text-emerald-700">
                      <BadgeCheck className="w-3 h-3" /> {s.tier_label}
                    </span>
                  )}
                </span>
                {s.url && <ExternalLink className="inline w-3 h-3 ml-1 text-slate-300" />}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
