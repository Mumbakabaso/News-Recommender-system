import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Flame, Hash, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import RegionToggle from '../components/RegionToggle'
import TrendingStoryCard, { storyHref } from '../components/TrendingStoryCard'
import { useRegion } from '../hooks/useRegion'
import { timeAgo } from '../lib/time'

const WINDOWS = [
  { hours: 24, label: 'Last 24 hours' },
  { hours: 48, label: 'Last 2 days' },
  { hours: 168, label: 'This week' },
]

// Full trending page: every hot story with the coverage from each outlet.
export default function Trending() {
  const [region, setRegion] = useRegion()
  const [hours, setHours] = useState(48)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    setData(null)
    setError(null)
    api.getTrending({ region, hours, limit: 20 }).then(setData).catch((e) => setError(e.message))
  }, [region, hours])

  const handleOpen = (articleId) => {
    api.logInteraction({ articleId, eventType: 'click' }).catch(() => {})
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex items-center gap-2 mb-1">
        <Flame className="w-5 h-5 text-orange-500" />
        <h1 className="text-xl font-semibold text-slate-900">Trending now</h1>
      </div>
      <p className="text-sm text-slate-500 mb-5">
        Stories that several news outlets are covering at the same time, plus breaking news such as deaths and
        disasters.
      </p>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <RegionToggle value={region} onChange={setRegion} />
        <select
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          className="text-sm border border-slate-200 rounded-lg bg-white px-3 py-2 text-slate-700"
          aria-label="Time window"
        >
          {WINDOWS.map((w) => (
            <option key={w.hours} value={w.hours}>{w.label}</option>
          ))}
        </select>
      </div>

      {error && <div className="text-red-600 bg-red-50 border border-red-200 rounded-lg p-4 text-sm">{error}</div>}
      {!data && !error && <div className="text-slate-400 py-16 text-center">Finding hot stories…</div>}

      {data && data.hot_topics.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-8">
          {data.hot_topics.map((t) => (
            <Link
              key={t.topic}
              to={`/search?q=${encodeURIComponent(t.topic)}`}
              className="flex items-center gap-1 text-sm px-2.5 py-1 rounded-full bg-orange-50 text-orange-700 hover:bg-orange-100"
              title={`Mentioned by ${t.source_count} sources`}
            >
              <Hash className="w-3 h-3" />
              {t.topic}
            </Link>
          ))}
        </div>
      )}

      {data && data.stories.length === 0 && (
        <div className="text-slate-400 py-16 text-center">
          Nothing is trending yet. Stories appear here once several sources cover the same event.
        </div>
      )}

      <div className="flex flex-col gap-6">
        {data?.stories.map((s, i) => (
          <article key={`${s.label}-${s.lead.id}`} className="grid md:grid-cols-[18rem_1fr] gap-4">
            <TrendingStoryCard story={s} rank={i + 1} onOpen={handleOpen} />
            {s.articles.length > 1 && (
              <div className="bg-white border border-slate-200 rounded-xl p-4">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    Coverage · {s.article_count} article{s.article_count === 1 ? '' : 's'}
                  </div>
                  <Link
                    to={storyHref(s)}
                    onClick={() => handleOpen(s.lead.id)}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 rounded-lg"
                  >
                    <Sparkles className="w-3.5 h-3.5" /> Read the briefing
                  </Link>
                </div>
                <ul className="divide-y divide-slate-100">
                  {s.articles.map((a) => (
                    <li key={a.id}>
                      <Link
                        to={`/article/${a.id}`}
                        onClick={() => handleOpen(a.id)}
                        className="flex items-start justify-between gap-3 py-2 group"
                      >
                        <span className="text-sm text-slate-800 group-hover:text-indigo-600 leading-snug">{a.title}</span>
                        <span className="shrink-0 text-xs text-slate-400 text-right">
                          {a.source_name}
                          <br />
                          {timeAgo(a.published_at)}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  )
}
