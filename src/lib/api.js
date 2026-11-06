// Central API client for the news recommender backend.
// All requests go through here so the RL feedback loop (interaction logging)
// stays consistent no matter which page triggers it.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api'

function getToken() {
  return localStorage.getItem('nr_token')
}

// Anonymous visitors still need a stable identity for the bandit's
// per-user context (see context/AuthContext.jsx's getOrCreateAnonId).
// Sent on every request; the backend only uses it when there's no JWT.
function getAnonId() {
  let id = localStorage.getItem('nr_anon_id')
  if (!id) {
    id = 'anon_' + Math.random().toString(36).slice(2) + Date.now().toString(36)
    localStorage.setItem('nr_anon_id', id)
  }
  return id
}

async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json', 'X-Anon-Id': getAnonId() }
  const token = getToken()
  if (auth && token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  let data = null
  try {
    data = await res.json()
  } catch {
    // no JSON body (e.g. 204)
  }

  if (!res.ok) {
    const message = data?.error || data?.message || `Request failed (${res.status})`
    throw new Error(message)
  }
  return data
}

export const api = {
  // --- auth ---
  register: (payload) => request('/auth/register', { method: 'POST', body: payload, auth: false }),
  login: (payload) => request('/auth/login', { method: 'POST', body: payload, auth: false }),
  me: () => request('/auth/me'),

  // --- onboarding / explicit interests ---
  getInterests: () => request('/users/me/interests'),
  saveInterests: (interests) => request('/users/me/interests', { method: 'PUT', body: { interests } }),

  // --- content ---
  getCategories: () => request('/categories', { auth: false }),
  // region: 'international' | 'zambia' | null (all); source: a key from getSources()
  getArticles: ({ category, region, source, q, page = 1, pageSize = 20 } = {}) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (region) params.set('region', region)
    if (source) params.set('source', source)
    if (q) params.set('q', q)
    params.set('page', page)
    params.set('page_size', pageSize)
    return request(`/articles?${params.toString()}`, { auth: false })
  },
  // Full article (body + publisher link) — needs an account.
  getArticle: (id) => request(`/articles/${id}`),

  // --- smart summaries ---
  // In-app summary of an article, combined with other outlets' coverage of
  // the same story when there is any. First request per story can take a
  // few seconds while the backend reads the pages and writes the summary.
  getArticleSummary: (id, { related = true } = {}) =>
    request(`/articles/${id}/summary${related ? '' : '?related=0'}`),
  // One combined summary of several articles (first id = lead), e.g. a trending story.
  getStorySummary: (ids) => request(`/stories/summary?ids=${ids.join(',')}`),

  // --- AI People Profiles ---
  // People mentioned in an article, each with `link_forms`: the exact
  // strings to turn into clickable names. Needs an account, like the article.
  getArticlePeople: (id) => request(`/articles/${id}/people`),
  // Full profile; the first request for someone can take a few seconds
  // while sources are gathered and the profile is written.
  getPerson: (key) => request(`/people/${encodeURIComponent(key)}`, { auth: false }),
  getPersonDevelopments: (id, page = 1) => request(`/people/${id}/developments?page=${page}`, { auth: false }),
  getPersonArticles: (id) => request(`/people/${id}/articles`, { auth: false }),
  listPeople: ({ q, zambian, inNews, page = 1, pageSize = 24 } = {}) => {
    const params = new URLSearchParams({ page, page_size: pageSize })
    if (q) params.set('q', q)
    if (zambian) params.set('zambian', '1')
    if (inNews) params.set('in_news', '1')
    return request(`/people?${params.toString()}`, { auth: false })
  },
  refreshPerson: (id) => request(`/people/${id}/refresh`, { method: 'POST' }),

  // --- recommendations (RL-powered) ---
  // Signed-in, onboarded users only: scored on their own history + interests.
  // region narrows the candidate articles; the bandit still chooses the topic mix.
  getRecommendations: ({ count = 10, region } = {}) =>
    request(`/recommendations?count=${count}${region ? `&region=${region}` : ''}`),

  // --- explicit feedback: like (1) / dislike (-1) / clear (0) ---
  setFeedback: (articleId, value) =>
    request(`/articles/${articleId}/feedback`, { method: 'PUT', body: { value } }),
  getMyFeedback: ({ value = 'like', page = 1, pageSize = 24 } = {}) =>
    request(`/users/me/feedback?value=${value}&page=${page}&page_size=${pageSize}`),

  // --- search & trending ---
  search: ({ q, region, category, page = 1, pageSize = 20 } = {}) => {
    const params = new URLSearchParams({ q, page, page_size: pageSize })
    if (region) params.set('region', region)
    if (category) params.set('category', category)
    return request(`/search?${params.toString()}`, { auth: false })
  },
  getTrending: ({ region, limit = 10, hours = 48 } = {}) => {
    const params = new URLSearchParams({ limit, hours })
    if (region) params.set('region', region)
    return request(`/trending?${params.toString()}`, { auth: false })
  },

  // --- live news sources (BBC, Al Jazeera, CNN, Zambian outlets) ---
  getSources: () => request('/sources', { auth: false }),
  refreshSources: () => request('/sources/refresh', { method: 'POST' }),

  // --- interaction / reward logging ---
  // Only signed-in readers' clicks and reading time are used as reward
  // signal, so skip the call entirely for logged-out visitors.
  logInteraction: ({ articleId, eventType, dwellSeconds = 0, position = null }) =>
    getToken()
      ? request('/interactions', {
          method: 'POST',
          body: { article_id: articleId, event_type: eventType, dwell_seconds: dwellSeconds, position },
        })
      : Promise.resolve(null),

  // --- admin / analytics ---
  getAnalytics: () => request('/admin/analytics'),
}

export { getToken, getAnonId }
