import { useEffect, useState } from 'react'

// Remembers the International / Zambia / All choice across pages and visits.
const KEY = 'nr_region'
const VALID = ['international', 'zambia']

function read() {
  try {
    const v = localStorage.getItem(KEY)
    return VALID.includes(v) ? v : null
  } catch {
    return null
  }
}

export function useRegion() {
  const [region, setRegion] = useState(read)
  useEffect(() => {
    try {
      if (region) localStorage.setItem(KEY, region)
      else localStorage.removeItem(KEY)
    } catch {
      // storage unavailable — the choice just won't persist
    }
  }, [region])
  return [region, setRegion]
}
