import { Play, Square } from "lucide-react"
import { useMonitoring } from "@/contexts/MonitoringContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface MonitoringControlsProps {
  compact?: boolean
}

export default function MonitoringControls({ compact = false }: MonitoringControlsProps) {
  const { settings, toggling, startMonitoring, stopMonitoring } = useMonitoring()
  const { t } = useLanguage()

  const isOn = settings?.is_enabled ?? false

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <StatusDot on={isOn} t={t} />
        {isOn ? (
          <Button
            variant="destructive"
            size="sm"
            onClick={stopMonitoring}
            disabled={toggling}
            className="gap-1.5 font-semibold shadow-sm"
          >
            {toggling ? <Spinner className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5 fill-current" />}
            {t("common.stop")}
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={startMonitoring}
            disabled={toggling}
            className="gap-1.5 font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
          >
            {toggling ? <Spinner className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5 fill-current" />}
            {t("common.start")}
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
      <div className={cn(
        "flex items-center gap-3 rounded-xl border px-4 py-3 min-w-[180px]",
        isOn ? "border-emerald-500/30 bg-emerald-500/5" : "border-border bg-muted/30"
      )}>
        <StatusDot on={isOn} large t={t} />
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{t("bot.label")}</p>
          <p className={cn(
            "text-sm font-bold",
            isOn ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"
          )}>
            {isOn ? t("common.on") : t("common.off")}
          </p>
        </div>
      </div>

      {isOn ? (
        <Button
          variant="destructive"
          size="lg"
          onClick={stopMonitoring}
          disabled={toggling}
          className="gap-2 font-semibold min-w-[160px] shadow-md"
        >
          {toggling ? <Spinner /> : <Square className="h-4 w-4 fill-current" />}
          {t("common.stop")}
        </Button>
      ) : (
        <Button
          size="lg"
          onClick={startMonitoring}
          disabled={toggling}
          className="gap-2 font-semibold min-w-[160px] bg-emerald-600 hover:bg-emerald-700 text-white shadow-md"
        >
          {toggling ? <Spinner /> : <Play className="h-4 w-4 fill-current" />}
          {t("common.start")}
        </Button>
      )}
    </div>
  )
}

function StatusDot({
  on,
  large,
  t,
}: {
  on: boolean
  large?: boolean
  t: (key: string) => string
}) {
  const size = large ? "h-10 w-10" : "h-2 w-2"
  if (large) {
    return (
      <div className={cn(
        "flex items-center justify-center rounded-full",
        on ? "bg-emerald-500/15" : "bg-muted"
      )}>
        <span className={cn(
          "h-3 w-3 rounded-full",
          on ? "bg-emerald-500 animate-pulse" : "bg-red-500"
        )} />
      </div>
    )
  }
  return (
    <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-muted/50 border border-border">
      <span className={cn(
        size,
        "rounded-full",
        on ? "bg-emerald-500 animate-pulse" : "bg-red-500"
      )} />
      <span className="text-xs font-medium hidden sm:inline">
        {on ? t("common.on") : t("common.off")}
      </span>
    </div>
  )
}
