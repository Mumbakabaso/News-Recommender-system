import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { RefreshCcw, CheckCircle2, XCircle, CircleDashed } from 'lucide-react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

// Surfaces the RL engine's own operational metrics: reward trend over time
// (is the bandit actually improving?) and per-category CTR, which is the
// evaluation angle the dissertation's methodology chapter calls for.
export default function Analytics() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getAnalytics().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="max-w-6xl mx-auto px-4 py-8 text-red-600">{error}</div>
  if (!data) return <div className="max-w-6xl mx-auto px-4 py-8 text-slate-400">Loading analytics…</div>

  const { summary, reward_over_time, ctr_by_category, arm_performance } = data

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 flex flex-col gap-8">
      <h1 className="text-xl font-semibold text-slate-900">Recommendation engine analytics</h1>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard label="Total interactions" value={summary.total_interactions} />
        <StatCard label="Total clicks" value={summary.total_clicks} />
        <StatCard label="Overall CTR" value={`${(summary.overall_ctr * 100).toFixed(1)}%`} />
        <StatCard label="Avg. reward / rec" value={summary.avg_reward.toFixed(3)} />
        <StatCard label="Likes" value={summary.total_likes ?? 0} />
        <StatCard label="Dislikes" value={summary.total_dislikes ?? 0} />
      </div>

      <section>
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Mean reward over time (bandit learning curve)</h2>
        <div className="h-64 bg-white border border-slate-200 rounded-xl p-4">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={reward_over_time}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="avg_reward" stroke="#4f46e5" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Click-through rate by category</h2>
        <div className="h-64 bg-white border border-slate-200 rounded-xl p-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={ctr_by_category}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="category" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="ctr" fill="#4f46e5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <NewsSources />

      <section>
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Bandit arm (category) selection frequency</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden">
            <thead className="bg-slate-50 text-slate-500 text-left">
              <tr>
                <th className="px-4 py-2">Category</th>
                <th className="px-4 py-2">Times recommended</th>
                <th className="px-4 py-2">Times clicked</th>
                <th className="px-4 py-2">Est. CTR</th>
                <th className="px-4 py-2">Users interested</th>
                <th className="px-4 py-2">Likes</th>
                <th className="px-4 py-2">Dislikes</th>
              </tr>
            </thead>
            <tbody>
              {arm_performance.map((row) => (
                <tr key={row.category} className="border-t border-slate-100">
                  <td className="px-4 py-2 capitalize">{row.category}</td>
                  <td className="px-4 py-2">{row.recommended}</td>
                  <td className="px-4 py-2">{row.clicked}</td>
                  <td className="px-4 py-2">{(row.ctr * 100).toFixed(1)}%</td>
                  <td className="px-4 py-2">{row.interested_users ?? 0}</td>
                  <td className="px-4 py-2 text-emerald-700">{row.likes ?? 0}</td>
                  <td className="px-4 py-2 text-rose-700">{row.dislikes ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-2xl font-semibold text-slate-900 mt-1">{value}</div>
    </div>
  )
}

// Live status of every news feed (BBC, Al Jazeera, CNN, Zambian outlets),
// with a button to fetch fresh articles immediately.
function NewsSources() {
  const [data, setData] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [message, setMessage] = useState(null)

  const load = () => api.getSources().then(setData).catch((e) => setMessage(e.message))
  useEffect(() => {
    load()
  }, [])

  const refresh = async () => {
    setRefreshing(true)
    setMessage(null)
    try {
      const r = await api.refreshSources()
      setMessage(`Fetched ${r.total_saved} articles.`)
    } catch (e) {
      setMessage(e.message)
    } finally {
      setRefreshing(false)
      load()
    }
  }

  const lastRun = data?.last_run?.finished_at

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-700">News sources</h2>
        <div className="flex items-center gap-3">
          {message && <span className="text-xs text-slate-500">{message}</span>}
          <button
            onClick={refresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-sm font-medium bg-slate-900 text-white px-3 py-1.5 rounded-md hover:bg-slate-700 disabled:opacity-60"
          >
            <RefreshCcw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Fetching…' : 'Fetch news now'}
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border border-slate-200 rounded-xl overflow-hidden bg-white">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2">Source</th>
              <th className="px-4 py-2">Region</th>
              <th className="px-4 py-2">Articles stored</th>
              <th className="px-4 py-2">Last fetch</th>
            </tr>
          </thead>
          <tbody>
            {(data?.sources || []).map((s) => (
              <tr key={s.key} className="border-t border-slate-100 align-top">
                <td className="px-4 py-2">
                  <div className="font-medium text-slate-800">{s.name}</div>
                  <div className="text-xs text-slate-400">{s.key}</div>
                </td>
                <td className="px-4 py-2 capitalize">{s.region}</td>
                <td className="px-4 py-2">{s.article_count}</td>
                <td className="px-4 py-2">
                  {!s.enabled ? (
                    <span className="text-slate-400">Disabled</span>
                  ) : s.ok === true ? (
                    <span className="flex items-center gap-1 text-emerald-700">
                      <CheckCircle2 className="w-4 h-4" /> OK · {s.last_saved} new/updated
                    </span>
                  ) : s.ok === false ? (
                    <span className="flex items-start gap-1 text-red-600">
                      <XCircle className="w-4 h-4 shrink-0 mt-0.5" /> {s.error}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-slate-400">
                      <CircleDashed className="w-4 h-4" /> Not fetched yet
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-400 mt-2">
        {lastRun ? `Last refresh: ${new Date(lastRun).toLocaleString()}. ` : ''}
        {data?.mock_articles ? `${data.mock_articles} sample (mock) articles are also stored.` : ''}
      </p>
    </section>
  )
}
