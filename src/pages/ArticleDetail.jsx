import { useEffect, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../lib/api'
import FeedbackButtons from '../components/FeedbackButtons'
import SummaryPanel from '../components/SummaryPanel'
import LinkedText from '../components/people/LinkedText'
import { useReadingTimer } from '../hooks/useReadingTimer'
import { ArrowLeft, ExternalLink } from 'lucide-react'

export default function ArticleDetail() {
  const { id } = useParams()
  const [article, setArticle] = useState(null)
  const [error, setError] = useState(null)
  const [feedbackNote, setFeedbackNote] = useState(null)
  const [people, setPeople] = useState([])

  useEffect(() => {
    setArticle(null)
    setError(null)
    setFeedbackNote(null)
    setPeople([])
    api.getArticle(id).then(setArticle).catch((e) => setError(e.message))
    // People mentioned in the story -> clickable names (never blocks the article).
    api.getArticlePeople(id).then((d) => setPeople(d.people || [])).catch(() => {})
  }, [id])

  const reportDwell = useCallback(
    (seconds) => {
      if (seconds < 1) return
      api.logInteraction({ articleId: id, eventType: 'read', dwellSeconds: seconds }).catch(() => {})
    },
    [id],
  )
  useReadingTimer(reportDwell)

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-10 text-red-600">Couldn't load article: {error}</div>
    )
  }
  if (!article) {
    return <div className="max-w-2xl mx-auto px-4 py-10 text-slate-400">Loading…</div>
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <Link to="/" className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-6">
        <ArrowLeft className="w-4 h-4" /> Back
      </Link>

      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide mb-2">
        <span className="text-indigo-600">{article.category?.replace('-', ' ')}</span>
        {article.region === 'zambia' && <span className="text-emerald-700">· Zambia</span>}
      </div>
      <h1 className="text-2xl font-bold text-slate-900 leading-snug mb-3">
        <LinkedText text={article.title} people={people} />
      </h1>
      <div className="text-sm text-slate-400 mb-6">
        {article.source_name}
        {article.published_at && <> · {new Date(article.published_at).toLocaleString()}</>}
      </div>

      {article.image_url && (
        <img src={article.image_url} alt="" className="w-full rounded-xl mb-6 object-cover" />
      )}

      {/* The story itself, readable here: a summary of this article, combined
          with other outlets' coverage of the same story when there is any. */}
      <SummaryPanel
        loadKey={id}
        load={() => api.getArticleSummary(id)}
        currentArticleId={article.id}
        people={people}
      />

      {article.url && (
        <a
          href={article.url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-indigo-600"
        >
          Read the original on {article.source_name || 'the source site'} <ExternalLink className="w-3.5 h-3.5" />
        </a>
      )}

      <section className="mt-10 border-t border-slate-200 pt-6">
        <h2 className="text-sm font-semibold text-slate-800 mb-1">Want more stories like this?</h2>
        <p className="text-sm text-slate-500 mb-4">
          Your answer goes straight into your For You feed.
        </p>
        <FeedbackButtons
          size="lg"
          articleId={article.id}
          value={article.my_feedback}
          onChange={(v) => {
            setArticle((a) => ({ ...a, my_feedback: v }))
            const topic = article.category?.replace('-', ' ')
            setFeedbackNote(
              v === 1
                ? `Thanks! You'll see more ${topic} stories.`
                : v === -1
                  ? `Got it. You'll see fewer stories like this, and this one won't be recommended again.`
                  : null,
            )
          }}
        />
        {feedbackNote && <p className="text-sm text-slate-600 mt-3" role="status">{feedbackNote}</p>}
      </section>
    </div>
  )
}
