import { useEffect, useState } from "react"
import { ImageIcon } from "lucide-react"
import { resolveProductImageUrl } from "@/lib/productImage"

export default function ProductImage({ src, alt = "" }: { src: string | null | undefined; alt?: string }) {
  const [failed, setFailed] = useState(false)
  const resolved = resolveProductImageUrl(src)

  useEffect(() => {
    setFailed(false)
  }, [resolved])

  if (!resolved || failed) {
    return (
      <div className="h-12 w-12 rounded-lg bg-muted flex items-center justify-center shrink-0">
        <ImageIcon className="h-5 w-5 text-muted-foreground" />
      </div>
    )
  }

  return (
    <img
      src={resolved}
      alt={alt}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      className="h-12 w-12 rounded-lg object-cover border border-border shrink-0 bg-muted"
      onError={() => setFailed(true)}
    />
  )
}
