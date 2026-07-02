// Normalise any API payload into an array — the app-wide guard against
// the "dict poisons a list state" crash class.
//
// Backend endpoints answer in three shapes:
//   1. a plain list                     → [...]
//   2. DRF pagination                   → { results: [...], count, ... }
//   3. a named envelope                 → { announcements: [...] } / { settings: [...] }
//
// The old inline idiom (results-or-data-or-empty) handled 1 and 2 but
// stored the whole DICT for shape 3 — then the first `.map()`/`.slice()` on
// it threw and the page died (that exact crash: Admin → Definições, where
// /collections/announcements/ returns {announcements: []}).
//
// asList() accepts every shape: array as-is, `results` if present, any
// caller-preferred keys, otherwise the first array-valued property of the
// envelope. Anything else (null, string, number, error body) becomes [].
export function asList(data, ...preferredKeys) {
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object') {
    if (Array.isArray(data.results)) return data.results
    for (const key of preferredKeys) {
      if (Array.isArray(data[key])) return data[key]
    }
    for (const value of Object.values(data)) {
      if (Array.isArray(value)) return value
    }
  }
  return []
}

export default asList
