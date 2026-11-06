import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Flame } from 'lucide-react'
import { api } from '../lib/api'
import SummaryPanel from '../components/SummaryPanel'
import FeedbackButtons from '../components/FeedbackButtons'
import { useReadingTimer } from '../hooks/useReadingTimer'

// /story?ids=12,45,78&label=Kafue%20floods
// One briefing for a story several outlets are covering (opened from the
// Trending section): their reporting combined into a single read.
export default function StoryBriefing() {
  const [params] = useSearchParams()
  const label = params.get('label')
  const ids = useMemo(
    () =>
      (params.get('ids') || '')
        .split(',')
        .map((x) => parseInt(x, 10))
        .filter((n) => Number.isFinite(n)),
    [params],
  )
  const leadId = ids[0]
  const [lead, setLead] = useState(null)
  const [feedback, setFeedback] = useState(0)
  const [people, setPeople] = useState([])

  // People across every outlet's article in the story, merged per person.
  useEffect(() => {
    let cancelled = false
    setPeople([])
    Promise.all(ids.slice(0, 6).map((i) => api.getArticlePeople(i).catch(() => ({ people: [] })))).then((rs) => {
      if (cancelled) return
      const byId = new Map()
      for (const r of rs) {
        for (const p of r.people || []) {
          const cur = byId.get(p.id)
          if (cur) cur.link_forms = [...new Set([...cur.link_forms, ...p.link_forms])]
          else byId.set(p.id, { ...p, link_forms: [...(p.link_forms || [])] })
        }
      }
      setPeople([...byId.values()])
    })
    return () => {
      cancelled = true
    }
  }, [ids])

  // Reading time counts toward the lead article, like reading it directly.
  const reportDwell = useCallback(
    (seconds) => {
      if (seconds < 1 || !leadId) return
      api.logInteraction({ articleId: leadId, eventType: 'read', dwellSeconds: seconds }).catch(() => {})
    },
    [leadId],
  )
  useReadingTimer(reportDwell)

  const onLoaded = useCallback(
    (s) => {
      // Pick up the lead article's image and the reader's like/dislike.
      if (!leadId) return
      api
        .getArticle(leadId)
        .then((a) => {
          setLead(a)
          setFeedback(a.my_feedback || 0)
        })
        .catch(() => setLead({ id: leadId, title: s.title }))
    },
    [leadId],
  )

  if (!ids.length) {
    return <div className="max-w-2xl mx-auto px-4 py-10 text-slate-500">No story selected.</div>
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <Link to="/trending" className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 mb-6">
        <ArrowLeft className="w-4 h-4" /> Trending
      </Link>

      {label && (
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-orange-600 mb-3">
          <Flame className="w-4 h-4" /> {label}
        </div>
      )}

      {lead?.image_url && (
        <img
          src={lead.image_url}
          alt=""
          className="w-full rounded-xl mb-6 object-cover max-h-96"
          onError={(e) => {
            e.currentTarget.style.display = 'none'
          }}
        />
      )}

      <SummaryPanel
        loadKey={ids.join(',')}
        load={() => api.getStorySummary(ids)}
        showTitle
        onLoaded={onLoaded}
        people={people}
      />

      {lead?.category && (
        <section className="mt-10 border-t border-slate-200 pt-6">
          <h2 className="text-sm font-semibold text-slate-800 mb-1">Want more stories like this?</h2>
          <p className="text-sm text-slate-500 mb-4">Your answer goes straight into your For You feed.</p>
          <FeedbackButtons size="lg" articleId={leadId} value={feedback} onChange={setFeedback} />
        </section>
      )}
    </div>
  )
}
