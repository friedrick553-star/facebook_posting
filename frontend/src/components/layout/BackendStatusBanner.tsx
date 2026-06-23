import { useEffect, useState } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"
import { checkBackendHealth } from "@/lib/api"
import { useLanguage } from "@/contexts/LanguageContext"
import { Button } from "@/components/ui/button"

export default function BackendStatusBanner() {
  const [online, setOnline] = useState(true)
  const [checking, setChecking] = useState(false)
  const [, setFailCount] = useState(0)
  const { t } = useLanguage()

  const ping = async () => {
    setChecking(true)
    const ok = await checkBackendHealth()
    if (ok) {
      setFailCount(0)
      setOnline(true)
    } else {
      setFailCount((c) => {
        const next = c + 1
        if (next >= 5) setOnline(false)
        return next
      })
    }
    setChecking(false)
  }

  useEffect(() => {
    ping()
    const id = setInterval(ping, 8000)
    return () => clearInterval(id)
  }, [])

  if (online) return null

  return (
    <div className="mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
      <div className="flex items-start gap-2 text-destructive">
        <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
        <div>
          <p className="font-semibold">{t("backend.offlineTitle")}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {t("backend.offlineHint")}
          </p>
        </div>
      </div>
      <Button variant="outline" size="sm" onClick={ping} disabled={checking} className="shrink-0">
        <RefreshCw className={`h-3.5 w-3.5 ${checking ? "animate-spin" : ""}`} />
        {t("common.retry")}
      </Button>
    </div>
  )
}
