import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Feed from './Feed'
import PublicHome from './PublicHome'

// "/" — the For You feed for signed-in users whose interests are set up;
// the public headlines page for everyone else.
export default function Home() {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-10 text-center text-slate-400">Loading...</div>
  if (!user) return <PublicHome />
  if (user.needs_onboarding) return <Navigate to="/onboarding" replace />
  return <Feed />
}
