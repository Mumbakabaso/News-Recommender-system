import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Landmark, TrendingUp, Cpu, Globe, Trophy, HeartPulse, Tag, Check, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { safeNext } from '../lib/redirect'

// Display details for the configured categories. Any slug not listed here
// (e.g. one added later through NEWS_CATEGORIES) still shows, with a
// generic icon.
const CATEGORY_META = {
  politics: { icon: Landmark, blurb: 'Government, elections, policy and parliament' },
  economics: { icon: TrendingUp, blurb: 'Markets, business, the kwacha and the cost of living' },
  technology: { icon: Cpu, blurb: 'Gadgets, startups, AI and the digital economy' },
  'global-affairs': { icon: Globe, blurb: 'International news, diplomacy and world events' },
  sports: { icon: Trophy, blurb: 'Football, athletics and results from home and abroad' },
  health: { icon: HeartPulse, blurb: 'Public health, medicine and wellbeing' },
}

const MIN_PICKS = 1

// Shown once, right after sign-up (and from "Edit interests" later).
// The categories picked here are stored as explicit interests and seed the
// RL recommender's cold-start context, so the very first feed is already
// personalised. The bandit then adapts from real clicks and reading time.
export default function Onboarding() {
  const { user, saveInterests } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const editing = params.get('edit') === '1' || (user && !user.needs_onboarding)
  // Where to go afterwards — e.g. the article they wanted to read before
  // signing up. Defaults to their new For You feed.
  const next = safeNext(params.get('next'), '/')

  const [categories, setCategories] = useState([])
  const [selected, setSelected] = useState(() => new Set(user?.interests || []))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .getCategories()
      .then((d) => setCategories(d.categories || []))
      .catch(() => setError('Could not load categories. Is the backend running?'))
  }, [])

  const toggle = (slug) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(slug)) next.delete(slug)
      else next.add(slug)
      return next
    })
  }

  const submit = async (interests) => {
    setSaving(true)
    setError(null)
    try {
      await saveInterests(interests)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  const allSelected = categories.length > 0 && selected.size === categories.length
  const canContinue = selected.size >= MIN_PICKS && !saving

  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 text-indigo-600 text-sm font-medium bg-indigo-50 px-3 py-1 rounded-full mb-4">
          <Sparkles className="w-4 h-4" />
          {editing ? 'Update your interests' : `Welcome${user?.name ? `, ${user.name.split(' ')[0]}` : ''}!`}
        </div>
        <h1 className="text-2xl sm:text-3xl font-semibold text-slate-900">What are you interested in?</h1>
        <p className="text-slate-500 mt-3 max-w-xl mx-auto">
          Pick the topics you want to read about. Your first recommendations are built from these, and they
          adapt as you read.
        </p>
      </div>

      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-slate-500">
          {selected.size} selected{selected.size < MIN_PICKS && ` · choose at least ${MIN_PICKS}`}
        </span>
        {categories.length > 0 && (
          <button
            type="button"
            onClick={() => setSelected(allSelected ? new Set() : new Set(categories.map((c) => c.slug)))}
            className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
          >
            {allSelected ? 'Clear all' : 'Select all'}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {categories.map((c) => {
          const meta = CATEGORY_META[c.slug] || { icon: Tag, blurb: '' }
          const Icon = meta.icon
          const active = selected.has(c.slug)
          return (
            <button
              key={c.slug}
              type="button"
              onClick={() => toggle(c.slug)}
              aria-pressed={active}
              className={`relative text-left rounded-xl border-2 p-5 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                active
                  ? 'border-indigo-600 bg-indigo-50 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
              }`}
            >
              <span
                className={`absolute top-3 right-3 w-6 h-6 rounded-full flex items-center justify-center border transition-colors ${
                  active ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-slate-300 text-transparent'
                }`}
              >
                <Check className="w-4 h-4" />
              </span>
              <div
                className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${
                  active ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'
                }`}
              >
                <Icon className="w-5 h-5" />
              </div>
              <div className="font-semibold text-slate-900">{c.name}</div>
              {meta.blurb && <div className="text-sm text-slate-500 mt-1">{meta.blurb}</div>}
            </button>
          )
        })}
      </div>

      {error && (
        <div className="mt-6 text-red-600 bg-red-50 border border-red-200 rounded-lg p-4 text-sm">{error}</div>
      )}

      <div className="mt-10 flex flex-col-reverse sm:flex-row items-center justify-between gap-4">
        {editing ? (
          <button
            type="button"
            onClick={() => navigate('/')}
            className="text-sm text-slate-500 hover:text-slate-900"
          >
            Cancel
          </button>
        ) : (
          // No skipping: the For You feed is only built from chosen interests.
          // People who aren't ready can still browse the public headlines.
          <button
            type="button"
            onClick={() => navigate('/categories')}
            className="text-sm text-slate-500 hover:text-slate-900"
          >
            Just browse headlines for now
          </button>
        )}
        <button
          type="button"
          disabled={!canContinue}
          onClick={() => submit([...selected])}
          className="w-full sm:w-auto bg-indigo-600 text-white rounded-md px-6 py-2.5 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving…' : editing ? 'Save interests' : 'Continue to my feed'}
        </button>
      </div>
    </div>
  )
}
