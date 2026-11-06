import { useEffect, useState } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { api } from '../lib/api'

// Like / dislike toggle for one article. Clicking the active button again
// clears the reaction. Updates instantly and rolls back if the save fails.
//   value     current reaction from the API (article.my_feedback): 1, -1 or 0
//   onChange  called with the new value after a successful save
//   size      'sm' for cards, 'lg' for the article page (shows labels)
export default function FeedbackButtons({ articleId, value = 0, onChange, size = 'sm' }) {
  const [current, setCurrent] = useState(value || 0)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setCurrent(value || 0)
  }, [value])

  const send = async (e, pressed) => {
    // Cards are links; don't open the article when a button is pressed.
    e.preventDefault()
    e.stopPropagation()
    if (busy) return
    const next = current === pressed ? 0 : pressed
    const previous = current
    setCurrent(next)
    setBusy(true)
    try {
      await api.setFeedback(articleId, next)
      onChange?.(next, previous)
    } catch {
      setCurrent(previous)
    } finally {
      setBusy(false)
    }
  }

  const lg = size === 'lg'
  const base = lg
    ? 'flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-colors'
    : 'p-1.5 rounded-md transition-colors'
  const icon = lg ? 'w-4 h-4' : 'w-4 h-4'

  return (
    <div className={`flex items-center ${lg ? 'gap-3' : 'gap-0.5'}`}>
      <button
        type="button"
        onClick={(e) => send(e, 1)}
        aria-pressed={current === 1}
        aria-label={current === 1 ? 'Remove like' : 'Like — show me more like this'}
        title="More like this"
        className={`${base} ${
          current === 1
            ? lg ? 'bg-emerald-600 border-emerald-600 text-white' : 'text-emerald-600 bg-emerald-50'
            : lg ? 'border-slate-200 text-slate-600 hover:bg-slate-50' : 'text-slate-400 hover:text-emerald-600 hover:bg-slate-100'
        }`}
      >
        <ThumbsUp className={icon} fill={current === 1 && !lg ? 'currentColor' : 'none'} />
        {lg && (current === 1 ? 'Liked' : 'More like this')}
      </button>
      <button
        type="button"
        onClick={(e) => send(e, -1)}
        aria-pressed={current === -1}
        aria-label={current === -1 ? 'Remove dislike' : 'Dislike — show me less like this'}
        title="Less like this"
        className={`${base} ${
          current === -1
            ? lg ? 'bg-rose-600 border-rose-600 text-white' : 'text-rose-600 bg-rose-50'
            : lg ? 'border-slate-200 text-slate-600 hover:bg-slate-50' : 'text-slate-400 hover:text-rose-600 hover:bg-slate-100'
        }`}
      >
        <ThumbsDown className={icon} fill={current === -1 && !lg ? 'currentColor' : 'none'} />
        {lg && (current === -1 ? 'Disliked' : 'Less like this')}
      </button>
    </div>
  )
}
