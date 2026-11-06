import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import ProtectedRoute from './components/ProtectedRoute'
import Home from './pages/Home'
import Categories from './pages/Categories'
import Search from './pages/Search'
import Trending from './pages/Trending'
import Liked from './pages/Liked'
import ArticleDetail from './pages/ArticleDetail'
import StoryBriefing from './pages/StoryBriefing'
import Login from './pages/Login'
import Register from './pages/Register'
import Onboarding from './pages/Onboarding'
import Analytics from './pages/admin/Analytics'
import People from './pages/People'
import PersonProfile from './pages/PersonProfile'
import { PeopleProvider } from './context/PeopleContext'

export default function App() {
  return (
    <PeopleProvider>
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <Routes>
        <Route path="/people" element={<People />} />
        <Route path="/people/:key" element={<PersonProfile />} />
        <Route path="/" element={<Home />} />
        <Route path="/categories" element={<Categories />} />
        <Route path="/search" element={<Search />} />
        <Route path="/trending" element={<Trending />} />
        <Route
          path="/liked"
          element={
            <ProtectedRoute>
              <Liked />
            </ProtectedRoute>
          }
        />
        <Route
          path="/article/:id"
          element={
            <ProtectedRoute reason="article">
              <ArticleDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/story"
          element={
            <ProtectedRoute reason="article">
              <StoryBriefing />
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/onboarding"
          element={
            <ProtectedRoute>
              <Onboarding />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute adminOnly>
              <Analytics />
            </ProtectedRoute>
          }
        />
      </Routes>
    </div>
    </PeopleProvider>
  )
}
