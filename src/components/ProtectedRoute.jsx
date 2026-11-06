import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { signupUrl } from '../lib/redirect'

// Guards a page behind an account.
//   reason           why the visitor is being sent to sign up (article | foryou),
//                    shown as a message on the sign-up page
//   requireOnboarded also require the user to have picked their interests
//   adminOnly        admin accounts only
export default function ProtectedRoute({ children, adminOnly = false, requireOnboarded = false, reason = 'login' }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  const here = location.pathname + location.search

  if (loading) return <div className="p-10 text-center text-slate-400">Loading...</div>
  if (!user) {
    // Existing pages (admin, onboarding) go to log in; content gates go to sign up.
    if (reason === 'login') return <Navigate to={`/login?next=${encodeURIComponent(here)}`} replace />
    return <Navigate to={signupUrl({ next: here, reason })} replace />
  }
  if (adminOnly && !user.is_admin) return <Navigate to="/" replace />
  if (requireOnboarded && user.needs_onboarding) {
    return <Navigate to={`/onboarding?next=${encodeURIComponent(here)}`} replace />
  }

  return children
}
