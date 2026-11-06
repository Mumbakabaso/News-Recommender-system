// Helpers for sending logged-out visitors to sign up and bringing them back
// to where they were afterwards (?next=/article/42).

// Only allow same-site paths, so ?next= can't be used to bounce people to
// another website after they log in.
export function safeNext(value, fallback = '/') {
  if (typeof value === 'string' && value.startsWith('/') && !value.startsWith('//')) return value
  return fallback
}

export function signupUrl({ next, reason } = {}) {
  const params = new URLSearchParams()
  if (next) params.set('next', next)
  if (reason) params.set('reason', reason)
  const qs = params.toString()
  return `/register${qs ? `?${qs}` : ''}`
}

// Shown at the top of the sign-up / log-in pages, depending on why the
// visitor was sent there.
export const REASON_MESSAGES = {
  article: 'Create a free account to read the full story.',
  foryou: 'Create a free account and pick your interests to get a news feed personalised for you.',
  login: 'Please log in to continue.',
}
