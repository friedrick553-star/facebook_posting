const cache = new Map<string, { data: unknown; at: number }>()
const DEFAULT_TTL_MS = 120_000

export function getCached<T>(key: string, ttlMs = DEFAULT_TTL_MS): T | null {
  const entry = cache.get(key)
  if (!entry || Date.now() - entry.at > ttlMs) return null
  return entry.data as T
}

export function setCached(key: string, data: unknown) {
  cache.set(key, { data, at: Date.now() })
}

export function invalidateCache(prefix?: string) {
  if (!prefix) {
    cache.clear()
    return
  }
  for (const key of cache.keys()) {
    if (key.startsWith(prefix)) cache.delete(key)
  }
}
