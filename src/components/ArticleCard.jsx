import { Link } from 'react-router-dom'
import { Clock, Tag, MapPin, Lock } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import FeedbackButtons from './FeedbackButtons'

// position/source are passed through so the click event carries enough
// context for the RL engine's reward attribution (which slot was clicked,
// was it a recommended vs. browsed article).
//   onFeedback(articleId, value)  optional — told when the reader likes/dislikes
//   dismissed / onUndo            optional — collapsed "less like this" state
export default function ArticleCard({ article, position, source = 'feed', onClick, highlight, onFeedback, dismissed, onUndo }) {
  const { user } = useAuth()
  const handleClick = () => {
    onClick?.({ articleId: article.id, position, source })
  }

  if (dismissed) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 text-center bg-slate-50 border border-dashed border-slate-300 rounded-xl p-6 min-h-40">
        <p className="text-sm text-slate-600">Got it. You'll see fewer stories like this.</p>
        <p className="text-xs text-slate-400 line-clamp-1">{article.title}</p>
        {onUndo && (
          <button type="button" onClick={() => onUndo(article.id)} className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
            Undo
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="group flex flex-col bg-white border border-slate-200 rounded-xl overflow-hidden hover:shadow-md transition-shadow">
    <Link
      to={`/article/${article.id}`}
      onClick={handleClick}
      className="flex flex-col flex-1"
    >
      <div className="aspect-[16/9] bg-slate-100 overflow-hidden">
        {article.image_url ? (
          <img
            src={article.image_url}
            alt=""
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-slate-300 text-xs">No image</div>
        )}
      </div>
      <div className="p-4 flex flex-col gap-2 flex-1">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-indigo-600 font-medium uppercase tracking-wide">
            <Tag className="w-3 h-3" />
            {article.category?.replace('-', ' ')}
          </div>
          {article.region === 'zambia' && (
            <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">
              <MapPin className="w-3 h-3" /> Zambia
            </span>
          )}
        </div>
        <h3 className="font-semibold text-slate-900 leading-snug line-clamp-3">
          <Highlight text={article.title} query={highlight} />
        </h3>
        <p className="text-sm text-slate-500 line-clamp-2 flex-1">
          <Highlight text={article.description} query={highlight} />
        </p>
        <div className="flex items-center justify-between text-xs text-slate-400 pt-2">
          <span className="font-medium text-slate-500">{article.source_name}</span>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatDate(article.published_at)}
          </span>
        </div>
        {!user && (
          <div className="flex items-center gap-1 text-xs text-indigo-600 font-medium pt-1">
            <Lock className="w-3 h-3" /> Sign up free to read
          </div>
        )}
        {article.recommendation_score != null && (
          <div className="text-[10px] text-slate-300 font-mono">
            score {article.recommendation_score.toFixed(3)}
          </div>
        )}
      </div>
    </Link>
      {/* Outside the link: buttons inside an <a> are invalid HTML. */}
      {user && (
        <div className="flex items-center justify-between px-3 py-1.5 border-t border-slate-100">
          <span className="text-[11px] text-slate-400">Your feedback</span>
          <FeedbackButtons
            articleId={article.id}
            value={article.my_feedback}
            onChange={(v) => onFeedback?.(article.id, v)}
          />
        </div>
      )}
    </div>
  )
}

// Marks the searched words in a title/summary (search results page).
function Highlight({ text, query }) {
  if (!text || !query) return text || null
  const words = query
    .replace(/["']/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length > 1 && !w.startsWith('-') && w.toUpperCase() !== 'OR')
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  if (!words.length) return text
  const re = new RegExp(`(${words.join('|')})`, 'gi')
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="bg-yellow-100 text-inherit rounded px-0.5">{part}</mark>
    ) : (
      part
    ),
  )
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const diffH = Math.round((Date.now() - d.getTime()) / 36e5)
  if (diffH < 1) return 'just now'
  if (diffH < 24) return `${diffH}h ago`
  return `${Math.round(diffH / 24)}d ago`
}
