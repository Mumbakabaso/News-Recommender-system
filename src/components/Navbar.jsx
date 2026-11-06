import { Link, NavLink } from 'react-router-dom'
import { Newspaper, LayoutDashboard, LogOut, User, Flame, Search, Lock } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import SearchBar from './SearchBar'
import { signupUrl } from '../lib/redirect'

export default function Navbar() {
  const { user, logout } = useAuth()

  const linkClass = ({ isActive }) =>
    `px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
      isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
    }`

  const links = (
    <>
      {user ? (
        <NavLink to="/" end className={linkClass}>For You</NavLink>
      ) : (
        <>
          <NavLink to="/" end className={linkClass}>Home</NavLink>
          {/* Visible to logged-out visitors, but leads to sign-up. */}
          <Link
            to={signupUrl({ next: '/', reason: 'foryou' })}
            className={linkClass({ isActive: false })}
            title="Create a free account to get your personalised feed"
          >
            <span className="flex items-center gap-1"><Lock className="w-3.5 h-3.5" /> For You</span>
          </Link>
        </>
      )}
      <NavLink to="/trending" className={linkClass}>
        <span className="flex items-center gap-1"><Flame className="w-4 h-4" /> Trending</span>
      </NavLink>
      <NavLink to="/categories" className={linkClass}>Categories</NavLink>
      {user?.is_admin && (
        <NavLink to="/admin" className={linkClass}>
          <span className="flex items-center gap-1"><LayoutDashboard className="w-4 h-4" /> Analytics</span>
        </NavLink>
      )}
    </>
  )

  return (
    <header className="border-b border-slate-200 bg-white sticky top-0 z-20">
      <div className="max-w-6xl mx-auto px-4 flex items-center justify-between gap-4 h-16">
        <Link to="/" className="flex items-center gap-2 font-semibold text-slate-900 shrink-0">
          <Newspaper className="w-5 h-5 text-indigo-600" />
          <span className="whitespace-nowrap">News Recommendation System</span>
        </Link>

        <nav className="hidden md:flex items-center gap-1">{links}</nav>

        <SearchBar className="hidden md:block flex-1 max-w-xs" />

        <div className="flex items-center gap-3 shrink-0">
          <Link to="/search" className="md:hidden p-2 text-slate-500 hover:text-slate-900" aria-label="Search">
            <Search className="w-5 h-5" />
          </Link>
          {user ? (
            <>
              <Link
                to="/liked"
                title="Your likes and dislikes"
                className="text-sm text-slate-500 hover:text-slate-900 hidden sm:flex items-center gap-1"
              >
                <User className="w-4 h-4" /> {user.name}
              </Link>
              <button
                onClick={logout}
                className="text-sm text-slate-500 hover:text-slate-900 flex items-center gap-1"
              >
                <LogOut className="w-4 h-4" /> Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="text-sm font-medium text-slate-600 hover:text-slate-900">
                Log in
              </Link>
              <Link
                to="/register"
                className="text-sm font-medium bg-indigo-600 text-white px-3 py-1.5 rounded-md hover:bg-indigo-700"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>

      {/* Small screens: the page links get their own scrollable row. */}
      <nav className="md:hidden flex items-center gap-1 px-4 pb-2 overflow-x-auto">{links}</nav>
    </header>
  )
}
