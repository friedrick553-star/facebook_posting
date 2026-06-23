import { cn } from "@/lib/utils"
import { useLanguage } from "@/contexts/LanguageContext"

export function Logo({ className, size = 40 }: { className?: string; size?: number }) {
  const { t } = useLanguage()
  return (
    <img
      src="/logo.svg"
      alt={t("app.title")}
      width={size}
      height={size}
      className={cn("rounded-xl shadow-sm", className)}
    />
  )
}

export function BrandTitle({ className }: { className?: string }) {
  const { t } = useLanguage()
  return (
    <div className={cn("flex flex-col", className)}>
      <span className="font-bold text-base leading-tight tracking-tight">
        {t("app.title")}
      </span>
      <span className="text-xs font-medium text-muted-foreground">
        {t("app.subtitle")}
      </span>
    </div>
  )
}
