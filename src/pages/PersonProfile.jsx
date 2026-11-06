import { useEffect, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, BadgeCheck, Newspaper, RotateCw, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import ProfileBody, { Avatar } from '../components/people/ProfileBody'
import ArticleCard from '../components/ArticleCard'

// /people/:key — the complete profile of one person (key = slug or id).
export default function PersonProfile() {
  const { key } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [articles, setArticles] = useState([])
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    api
      .getPerson(key)
      .then((d) => {
        if (cancelled) return
        setData(d)
        document.title = `${d.name} — News Recommendation System`
        api.getPersonArticles(d.id).then((r) => !cancelled && setArticles(r.articles)).catch(() => {})
      })
      .catch((e) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
      document.title = 'News Recommendation System'
    }
  }, [key, attempt])

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <button
        onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/people'))}
        className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-6"
      >
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      {error && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
          Couldn't load this profile: {error}{' '}
          <button onClick={() => setAttempt((n) => n + 1)} className="inline-flex items-center gap-1 font-medium underline">
            <RotateCw className="w-3.5 h-3.5" /> Try again
          </button>
        </div>
      )}

      {!data && !error && (
        <div className="flex items-center gap-2 text-sm text-indigo-700">
          <Sparkles className="w-4 h-4 animate-pulse" /> Gathering sources and preparing the profile…
        </div>
      )}

      {data && (
        <div className="grid lg:grid-cols-[1fr_300px] gap-8">
          <article className="min-w-0">
            <header className="flex flex-col sm:flex-row gap-5 sm:items-center mb-6">
              <Avatar person={data} size="lg" />
              <div className="min-w-0">
                <h1 className="text-3xl font-bold text-slate-900 leading-tight">{data.name}</h1>
                {(data.headline_position || data.short_description) && (
                  <p className={`mt-1 ${data.headline_position_current ? 'text-indigo-700 font-medium' : 'text-slate-600'}`}>
                    {data.headline_position || data.short_description}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {data.is_zambian && (
                    <span className="text-xs font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                      Zambia
                    </span>
                  )}
                  {data.verification === 'wikidata' ? (
                    <a
                      href={`https://www.wikidata.org/wiki/${data.wikidata_id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-slate-600 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded hover:border-slate-300"
                    >
                      <BadgeCheck className="w-3.5 h-3.5 text-sky-600" /> Identity matched to Wikidata
                    </a>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                      <Newspaper className="w-3.5 h-3.5" /> Based on news reports only
                    </span>
                  )}
                </div>
              </div>
            </header>
            <div className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-7 shadow-sm">
              <ProfileBody data={data} />
            </div>
          </article>

          <aside className="space-y-4">
            <h2 className="text-sm font-semibold text-slate-800">In the news on News Recommendation System</h2>
            {articles.length === 0 ? (
              <p className="text-sm text-slate-400">No articles in your feed mention {data.name} yet.</p>
            ) : (
              <div className="space-y-4">
                {articles.slice(0, 6).map((a) => (
                  <ArticleCard key={a.id} article={a} />
                ))}
              </div>
            )}
            <Link to="/people" className="block text-sm text-indigo-600 hover:underline">
              Browse all people →
            </Link>
          </aside>
        </div>
      )}
    </div>
  )
}
