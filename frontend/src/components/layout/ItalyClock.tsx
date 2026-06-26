import { useEffect, useState } from "react"
import { Clock } from "lucide-react"
import { formatItalyNow, italyUtcOffsetLabel, POSTING_TIMEZONE } from "@/lib/schedule"
import { useLanguage } from "@/contexts/LanguageContext"
import { cn } from "@/lib/utils"

export default function ItalyClock({ className }: { className?: string }) {
  const { t } = useLanguage()
  const [now, setNow] = useState(formatItalyNow())
  const [offset, setOffset] = useState(italyUtcOffsetLabel())

  useEffect(() => {
    const tick = () => {
      setNow(formatItalyNow())
      setOffset(italyUtcOffsetLabel())
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      className={cn(
        "hidden sm:flex items-center gap-2 rounded-lg border border-[#1877F2]/25 bg-[#1877F2]/5 px-2.5 py-1.5 shrink-0",
        className,
      )}
      title={t("clock.tooltip")}
    >
      <Clock className="h-3.5 w-3.5 text-[#1877F2] shrink-0" />
      <div className="leading-tight">
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">
          {t("clock.label")} ({offset})
        </p>
        <p className="text-xs font-semibold tabular-nums text-foreground">{now}</p>
      </div>
    </div>
  )
}

export { POSTING_TIMEZONE }
