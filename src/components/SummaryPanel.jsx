import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles, ListChecks, Lightbulb, Newspaper, ExternalLink, RotateCw, Clock } from 'lucide-react'
import { timeAgo } from '../lib/time'
import LinkedText, { buildMatcher } from './people/LinkedText'

// In-app "smart summary" of a story: one article, or several outlets'
// reporting combined into one read. `load` is a function returning a promise
// for the summary JSON from the API (getArticleSummary / getStorySummary).
//
//   showTitle         show the summary's own headline (story briefing page)
//   currentArticleId  marks "the article you opened" in the sources list
//   people            people mentioned in the story (GET /api/articles/<id>/people);
//                     their names become clickable profile links
export default function SummaryPanel({ load, loadKey, showTitle = false, currentArticleId = null, onLoaded, people }) {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const matcher = useMemo(() => buildMatcher(people), [people])

  useEffect(() => {
    let cancelled = false
    setSummary(null)
    setError(null)
    load()
      .then((s) => {
        if (cancelled) return
        setSummary(s)
        onLoaded?.(s)
      })
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadKey, attempt])

  if (error) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800 flex items-center justify-between gap-3">
        <span>Couldn't write a summary right now: {error}</span>
        <button
          onClick={() => setAttempt((n) => n + 1)}
          className="shrink-0 inline-flex items-center gap-1 font-medium text-amber-900 hover:underline"
        >
          <RotateCw className="w-3.5 h-3.5" /> Try again
        </button>
      </div>
    )
  }

  if (!summary) return <SummarySkeleton />

  const isAi = summary.engine === 'gemini'
  const combined = summary.sources.length > 1

  return (
    <section aria-label="Summary" className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 shadow-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs mb-4">
        <span className="inline-flex items-center gap-1.5 font-semibold text-indigo-700 bg-indigo-50 px-2.5 py-1 rounded-full">
          <Sparkles className="w-3.5 h-3.5" />
          {combined ? `Combined from ${summary.source_count} sources` : 'Summary'}
        </span>
        <span className="inline-flex items-center gap-1 text-slate-500">
          <Clock className="w-3.5 h-3.5" /> {summary.reading_minutes} min read
        </span>
        <span className="text-slate-400" title={isAi ? `Written by ${summary.model}` : 'Key sentences picked by the offline summariser'}>
          {isAi ? 'AI-written summary' : 'Key sentences from the reporting'}
        </span>
      </div>

      {showTitle && (
        <h1 className="text-2xl font-bold text-slate-900 leading-snug mb-4">
          <LinkedText text={summary.title} matcher={matcher} />
        </h1>
      )}

      {summary.key_points?.length > 0 && (
        <div className="bg-slate-50 rounded-xl p-4 mb-5">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
            <ListChecks className="w-4 h-4" /> Key points
          </div>
          <ul className="space-y-1.5">
            {summary.key_points.map((k, i) => (
              <li key={i} className="flex gap-2 text-[15px] text-slate-800 leading-snug">
                <span className="mt-2 w-1.5 h-1.5 rounded-full bg-indigo-500 shrink-0" />
                <span><LinkedText text={k} matcher={matcher} /></span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-4 text-[17px] leading-relaxed text-slate-800">
        {summary.paragraphs.map((p, i) => (
          <p key={i}>
            <LinkedText text={p} matcher={matcher} />
          </p>
        ))}
      </div>

      {summary.why_it_matters && (
        <div className="mt-5 flex gap-3 border-l-4 border-amber-400 bg-amber-50/60 rounded-r-lg p-3.5">
          <Lightbulb className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-amber-700 mb-0.5">Why it matters</div>
            <p className="text-[15px] text-slate-800 leading-snug"><LinkedText text={summary.why_it_matters} matcher={matcher} /></p>
          </div>
        </div>
      )}

      <div className="mt-6 pt-4 border-t border-slate-100">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
          <Newspaper className="w-4 h-4" /> Based on reporting from
        </div>
        <ul className="space-y-1.5">
          {summary.sources.map((s) => (
            <li key={s.id} className="flex items-start justify-between gap-3 text-sm">
              <span className="min-w-0">
                <span className="font-medium text-slate-700">{s.source_name}</span>
                <span className="text-slate-400"> · {timeAgo(s.published_at)}</span>
                {s.id !== currentArticleId ? (
                  <Link to={`/article/${s.id}`} className="block text-slate-600 hover:text-indigo-600 truncate">
                    {s.title}
                  </Link>
                ) : (
                  <span className="block text-slate-500 truncate">{s.title} (this article)</span>
                )}
              </span>
              {s.url && (
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-indigo-600 mt-0.5"
                  title={`Original article on ${s.source_name}`}
                >
                  Original <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </li>
          ))}
        </ul>
        {!isAi && summary.full_text_count === 0 && (
          <p className="text-xs text-slate-400 mt-3">
            The publisher's page couldn't be read, so this is based on the headline and teaser only.
          </p>
        )}
      </div>
    </section>
  )
}

function SummarySkeleton() {
  return (
    <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm" aria-busy="true">
      <div className="flex items-center gap-2 text-sm text-indigo-700 mb-5">
        <Sparkles className="w-4 h-4 animate-pulse" />
        Reading the coverage and writing your summary… (the first time can take a few seconds)
      </div>
      <div className="space-y-3 animate-pulse">
        {[100, 96, 88, 100, 92, 70].map((w, i) => (
          <div key={i} className="h-3.5 bg-slate-100 rounded" style={{ width: `${w}%` }} />
        ))}
      </div>
    </section>
  )
}
