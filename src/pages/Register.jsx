import { useState } from 'react'
import { useNavigate, Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { safeNext, REASON_MESSAGES } from '../lib/redirect'

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'), '/')
  const reason = params.get('reason')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await register(name, email, password)
      // New accounts pick their interests first, so the very first feed is
      // personalised instead of a generic cold-start one.
      // ...then onboarding sends them back to `next` (e.g. the article they
      // were trying to read).
      navigate(`/onboarding?next=${encodeURIComponent(next)}`, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto px-4 py-16">
      {REASON_MESSAGES[reason] && (
        <div className="mb-6 text-sm bg-indigo-50 text-indigo-800 border border-indigo-100 rounded-lg px-4 py-3">
          {REASON_MESSAGES[reason]}
        </div>
      )}
      <h1 className="text-xl font-semibold text-slate-900 mb-6">Create an account</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="register-name" className="text-sm font-medium text-slate-700">
            Full name
          </label>
          <input
            id="register-name"
            required
            placeholder="Jane Doe"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white text-slate-900 placeholder:text-slate-400"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="register-email" className="text-sm font-medium text-slate-700">
            Email
          </label>
          <input
            id="register-email"
            type="email"
            required
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white text-slate-900 placeholder:text-slate-400"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="register-password" className="text-sm font-medium text-slate-700">
            Password
          </label>
          <input
            id="register-password"
            type="password"
            required
            minLength={8}
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="border border-slate-300 rounded-md px-3 py-2 text-sm bg-white text-slate-900 placeholder:text-slate-400"
          />
        </div>
        {error && <div className="text-sm text-red-600">{error}</div>}
        <button
          type="submit"
          disabled={submitting}
          className="bg-indigo-600 text-white rounded-md py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {submitting ? 'Creating…' : 'Sign up'}
        </button>
      </form>
      <p className="text-sm text-slate-500 mt-4">
        Already have an account?{' '}
        <Link to={`/login?${params.toString()}`} className="text-indigo-600 font-medium">Log in</Link>
      </p>
    </div>
  )
}
