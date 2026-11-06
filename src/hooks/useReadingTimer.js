import { useEffect, useRef } from 'react'

// Tracks how long an article has been visibly on screen and reports the
// dwell time once, on unmount (or tab hide). This is the "reading time"
// reward signal the dissertation's methodology relies on for the bandit,
// as a proxy for implicit positive feedback beyond a raw click.
export function useReadingTimer(onReport) {
  const startRef = useRef(Date.now())
  const reportedRef = useRef(false)
  const accumulatedRef = useRef(0)

  useEffect(() => {
    startRef.current = Date.now()

    const handleVisibility = () => {
      if (document.hidden) {
        accumulatedRef.current += (Date.now() - startRef.current) / 1000
      } else {
        startRef.current = Date.now()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)

    const report = () => {
      if (reportedRef.current) return
      reportedRef.current = true
      if (!document.hidden) {
        accumulatedRef.current += (Date.now() - startRef.current) / 1000
      }
      onReport(Math.round(accumulatedRef.current))
    }

    window.addEventListener('beforeunload', report)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility)
      window.removeEventListener('beforeunload', report)
      report()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
