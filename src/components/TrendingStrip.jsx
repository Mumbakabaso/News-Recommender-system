import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Flame, ChevronRight, Hash } from 'lucide-react'
import { api } from '../lib/api'
import TrendingStoryCard from './TrendingStoryCard'

// "Trending now" row at the top of the home feed: stories several outlets
// are covering at once, plus hot-topic chips that open a search.
export default function TrendingStrip({ region }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    let cancelled = false
    api
      .getTrending({ region, limit: 8 })
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setData({ stories: [], hot_topics: [] }))
    return () => {
      cancelled = true
    }
  }, [region])

  if (!data || (!data.stories.length && !data.hot_topics.length)) return null

  const handleOpen = (articleId) => {
    api.logInteraction({ articleId, eventType: 'click' }).catch(() => {})
  }

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Flame className="w-5 h-5 text-orange-500" />
          <h2 className="text-lg font-semibold text-slate-900">Trending now</h2>
        </div>
        <Link to="/trending" className="flex items-center text-sm text-indigo-600 hover:text-indigo-700 font-medium">
          See all <ChevronRight className="w-4 h-4" />
        </Link>
      </div>

      {data.hot_topics.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {data.hot_topics.slice(0, 8).map((t) => (
            <Link
              key={t.topic}
              to={`/search?q=${encodeURIComponent(t.topic)}`}
              className="flex items-center gap-1 text-sm px-2.5 py-1 rounded-full bg-orange-50 text-orange-700 hover:bg-orange-100"
            >
              <Hash className="w-3 h-3" />
              {t.topic}
            </Link>
          ))}
        </div>
      )}

      {data.stories.length > 0 && (
        <div className="flex gap-4 overflow-x-auto pb-2 snap-x -mx-4 px-4">
          {data.stories.map((s, i) => (
            <TrendingStoryCard key={`${s.label}-${s.lead.id}`} story={s} rank={i + 1} onOpen={handleOpen} compact />
          ))}
        </div>
      )}
    </section>
  )
}
