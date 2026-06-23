/** Route external CSV image URLs through our backend so they always render in the UI. */
export function resolveProductImageUrl(url: string | null | undefined): string | undefined {
  if (!url?.trim()) return undefined
  const value = url.trim()
  if (value.startsWith("/api/products/image-proxy")) return value
  if (value.startsWith("/")) return value
  return `/api/products/image-proxy?url=${encodeURIComponent(value)}`
}
