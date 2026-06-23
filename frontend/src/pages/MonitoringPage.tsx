import { useEffect, useState } from "react"
import { RefreshCw, Clock } from "lucide-react"
import { getMonitoringSettings, updateMonitoringSettings } from "@/lib/api"
import type { MonitoringSettings } from "@/types"
import { Button } from "@/components/ui/button"
import { Input, Label } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge, Spinner } from "@/components/ui/badge"
import { useToast } from "@/contexts/ToastContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { SCAN_DELAY_PRESETS, formatDate, formatIntervalRange } from "@/lib/utils"

const DEFAULT_MIN = 30
const DEFAULT_MAX = 45

export default function MonitoringPage() {
  const [settings, setSettings] = useState<MonitoringSettings | null>(null)
  const [minSeconds, setMinSeconds] = useState(String(DEFAULT_MIN))
  const [maxSeconds, setMaxSeconds] = useState(String(DEFAULT_MAX))
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()
  const { language, t } = useLanguage()

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await getMonitoringSettings()
      setSettings(data)
      setMinSeconds(String(data.refresh_interval_min_seconds || DEFAULT_MIN))
      setMaxSeconds(String(data.refresh_interval_max_seconds || DEFAULT_MAX))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const save = async (updates: Parameters<typeof updateMonitoringSettings>[0]) => {
    setSaving(true)
    try {
      const { data } = await updateMonitoringSettings(updates)
      setSettings(data)
      setMinSeconds(String(data.refresh_interval_min_seconds || DEFAULT_MIN))
      setMaxSeconds(String(data.refresh_interval_max_seconds || DEFAULT_MAX))
      toast(t("monitoring.intervalSaved"), "success")
    } catch {
      toast(t("monitoring.saveFailed"), "error")
    } finally {
      setSaving(false)
    }
  }

  const saveDelayRange = async (minSec: number, maxSec: number) => {
    if (minSec < 30) {
      toast(t("monitoring.min30"), "warning")
      return
    }
    if (maxSec < minSec) {
      toast(t("monitoring.maxGteMin"), "warning")
      return
    }
    await save({
      refresh_interval_min_seconds: minSec,
      refresh_interval_max_seconds: maxSec,
    })
  }

  const applyCustomRange = () => {
    const minSec = Math.round(Number(minSeconds))
    const maxSec = Math.round(Number(maxSeconds))
    if (!Number.isFinite(minSec) || !Number.isFinite(maxSec)) {
      toast(t("monitoring.validNumbers"), "warning")
      return
    }
    saveDelayRange(minSec, maxSec)
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>

  const minSec = settings?.refresh_interval_min_seconds ?? DEFAULT_MIN
  const maxSec = settings?.refresh_interval_max_seconds ?? DEFAULT_MAX

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">{t("monitoring.title")}</h1>
        <p className="text-muted-foreground text-sm mt-1">{t("monitoring.subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>{t("monitoring.statusTitle")}</CardTitle>
            <CardDescription>{t("monitoring.statusDesc")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
              <div className={`h-3 w-3 rounded-full shrink-0 ${settings?.is_enabled ? "bg-success animate-pulse" : "bg-muted-foreground"}`} />
              <span className="text-sm font-medium">
                {settings?.is_enabled ? t("bot.onRunning") : t("bot.offPressStart")}
              </span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
              <span>
                {t("monitoring.lastCheck")}:{" "}
                <strong>{settings?.last_scan_at ? formatDate(settings.last_scan_at, language) : t("common.never")}</strong>
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("monitoring.currentInterval")}</CardTitle>
            <CardDescription>{t("monitoring.currentIntervalDesc")}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
              <RefreshCw className="h-5 w-5 text-[#1877F2] shrink-0" />
              <div>
                <p className="text-2xl font-bold tabular-nums">{formatIntervalRange(minSec, maxSec, language)}</p>
                <p className="text-xs text-muted-foreground mt-1">{t("monitoring.minSecondsHint")}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("monitoring.intervalTitle")}</CardTitle>
          <CardDescription>{t("monitoring.intervalDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {SCAN_DELAY_PRESETS.map((opt) => {
              const active = minSec === opt.min && maxSec === opt.max
              return (
                <Button
                  key={opt.label}
                  variant={active ? "default" : "outline"}
                  size="sm"
                  onClick={() => saveDelayRange(opt.min, opt.max)}
                  disabled={saving}
                >
                  {opt.label}
                </Button>
              )
            })}
          </div>

          <div className="flex flex-col sm:flex-row items-end gap-3 pt-4 border-t border-border">
            <div className="space-y-2 flex-1">
              <Label>{t("monitoring.minSeconds")}</Label>
              <Input type="number" min={30} step={1} value={minSeconds} onChange={(e) => setMinSeconds(e.target.value)} />
            </div>
            <div className="space-y-2 flex-1">
              <Label>{t("monitoring.maxSeconds")}</Label>
              <Input type="number" min={30} step={1} value={maxSeconds} onChange={(e) => setMaxSeconds(e.target.value)} />
            </div>
            <Button variant="secondary" onClick={applyCustomRange} disabled={saving}>
              {t("monitoring.saveInterval")}
            </Button>
          </div>

          <p className="text-sm text-muted-foreground">
            {t("common.active")}:{" "}
            <Badge variant="secondary">{formatIntervalRange(minSec, maxSec, language)}</Badge>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
