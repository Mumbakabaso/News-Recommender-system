import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { X, ArrowRight, BadgeCheck, Newspaper, RotateCw, Sparkles } from 'lucide-react'
import { api } from '../../lib/api'
import ProfileBody, { Avatar } from './ProfileBody'

// Slide-in profile panel: from the right on tablets/desktops, a bottom
// sheet on phones. Opens over the article, so the reader never leaves it.
// The header (name, position, photo) shows immediately from the card the
// article already has; the full profile loads underneath.
export default function PersonPanel({ card, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const closeRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    api
      .getPerson(card.slug || card.id)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [card.id, card.slug, attempt])

  // Escape closes; focus moves into the panel; page behind doesn't scroll.
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  const head = data || card
  const position = head.headline_position || head.short_description

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-labelledby="person-panel-title">
      <button
        type="button"
        aria-label="Close profile"
        onClick={onClose}
        className="absolute inset-0 bg-slate-900/30 backdrop-blur-[1px] animate-[fadeIn_.15s_ease-out]"
      />
      <aside
        className="absolute bg-white shadow-2xl flex flex-col
          inset-x-0 bottom-0 max-h-[88vh] rounded-t-2xl animate-[sheetUp_.22s_ease-out]
          sm:inset-y-0 sm:right-0 sm:left-auto sm:bottom-auto sm:h-full sm:max-h-none sm:w-[460px] sm:rounded-none sm:animate-[slideIn_.22s_ease-out]"
      >
        <div className="sm:hidden flex justify-center pt-2">
          <span className="w-10 h-1 rounded-full bg-slate-200" />
        </div>
        <header className="px-5 pt-4 pb-4 border-b border-slate-100 flex gap-4 items-start">
          <Avatar person={head} size="lg" />
          <div className="min-w-0 flex-1">
            <h2 id="person-panel-title" className="text-xl font-bold text-slate-900 leading-tight">
              {head.name}
            </h2>
            {position && (
              <p className={`mt-1 text-sm ${head.headline_position_current ? 'text-indigo-700 font-medium' : 'text-slate-600'}`}>
                {position}
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {head.is_zambian && (
                <span className="text-[11px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-1.5 py-px rounded">
                  Zambia
                </span>
              )}
              {head.verification === 'wikidata' ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-50 border border-slate-200 px-1.5 py-px rounded">
                  <BadgeCheck className="w-3 h-3 text-sky-600" /> Identity matched to Wikidata
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 px-1.5 py-px rounded">
                  <Newspaper className="w-3 h-3" /> Based on news reports
                </span>
              )}
            </div>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            className="p-1.5 -mr-1.5 -mt-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          {error ? (
            <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
              Couldn't load this profile: {error}
              <button
                onClick={() => setAttempt((n) => n + 1)}
                className="ml-2 inline-flex items-center gap-1 font-medium underline"
              >
                <RotateCw className="w-3.5 h-3.5" /> Try again
              </button>
            </div>
          ) : !data ? (
            <ProfileSkeleton />
          ) : (
            <ProfileBody data={data} compact />
          )}
        </div>

        <footer className="px-5 py-3 border-t border-slate-100 bg-white">
          <Link
            to={`/people/${head.slug || head.id}`}
            onClick={onClose}
            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 text-white text-sm font-medium py-2.5 hover:bg-slate-800"
          >
            View complete profile <ArrowRight className="w-4 h-4" />
          </Link>
        </footer>
      </aside>
    </div>
  )
}

function ProfileSkeleton() {
  return (
    <div aria-busy="true">
      <p className="flex items-center gap-2 text-sm text-indigo-700 mb-4">
        <Sparkles className="w-4 h-4 animate-pulse" />
        Gathering sources and preparing the profile… (the first time can take a few seconds)
      </p>
      <div className="space-y-3 animate-pulse">
        {[100, 94, 80].map((w, i) => (
          <div key={i} className="h-3.5 bg-slate-100 rounded" style={{ width: `${w}%` }} />
        ))}
        <div className="h-24 bg-slate-50 rounded-xl mt-4" />
        {[90, 70, 85, 60].map((w, i) => (
          <div key={`b${i}`} className="h-3 bg-slate-100 rounded" style={{ width: `${w}%` }} />
        ))}
      </div>
    </div>
  )
}
