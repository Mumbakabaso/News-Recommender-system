import { Link } from 'react-router-dom'
import { Flame, Zap } from 'lucide-react'
import { timeAgo } from '../lib/time'

const KIND_LABEL = { death: 'Death', disaster: 'Disaster', emergency: 'Emergency', politics: 'Politics' }

function sourcesLine(sources) {
  if (!sources?.length) return ''
  if (sources.length <= 2) return sources.join(', ')
  return `${sources.slice(0, 2).join(', ')} +${sources.length - 2}`
}

// Link to a trending story: stories covered by several articles open the
// combined briefing (one summary of all the coverage); single articles open
// the article page.
export function storyHref(story) {
  const ids = (story.articles || []).map((a) => a.id)
  if (ids.length > 1) {
    return `/story?ids=${ids.join(',')}&label=${encodeURIComponent(story.label || '')}`
  }
  return `/article/${story.lead.id}`
}

// One trending story: the lead article's image and headline, the story label,
// and which outlets are covering it.
export default function TrendingStoryCard({ story, rank, onOpen, compact = false }) {
  const lead = story.lead
  return (
    <Link
      to={storyHref(story)}
      onClick={() => onOpen?.(lead.id)}
      className={`group flex flex-col bg-white border border-slate-200 rounded-xl overflow-hidden hover:shadow-md transition-shadow ${
        compact ? 'w-72 shrink-0 snap-start' : ''
      }`}
    >
      <div className="relative aspect-[16/9] bg-slate-100 overflow-hidden">
        {lead.image_url && (
          <img
            src={lead.image_url}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
        )}
        <div className="absolute top-2 left-2 flex gap-1.5">
          {rank != null && (
            <span className="bg-slate-900/80 text-white text-xs font-semibold px-2 py-0.5 rounded-md">#{rank}</span>
          )}
          {story.is_breaking && (
            <span className="flex items-center gap-1 bg-red-600 text-white text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-md">
              <Zap className="w-3 h-3" /> Breaking
            </span>
          )}
        </div>
      </div>
      <div className="p-3.5 flex flex-col gap-1.5 flex-1">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-orange-600">
          <Flame className="w-3.5 h-3.5" />
          <span className="truncate">{story.label}</span>
          {story.kind && !story.is_breaking && (
            <span className="text-slate-400 font-normal">· {KIND_LABEL[story.kind] || story.kind}</span>
          )}
        </div>
        <h3 className="font-semibold text-slate-900 leading-snug line-clamp-3 text-[15px]">{lead.title}</h3>
        <div className="mt-auto pt-1 text-xs text-slate-500 flex items-center justify-between gap-2">
          <span className="truncate">
            {story.source_count > 1 ? `${story.source_count} sources: ` : ''}
            {sourcesLine(story.sources)}
          </span>
          <span className="shrink-0 text-slate-400">{timeAgo(story.latest_at)}</span>
        </div>
      </div>
    </Link>
  )
}
