import { Package, CalendarClock, CheckCircle2, AlertTriangle, Copy, FileWarning } from "lucide-react"
import { Link } from "react-router-dom"
import { useProductsData } from "@/contexts/ProductsDataContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { StatCard } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

export default function DashboardPage() {
  const { t } = useLanguage()
  const { stats } = useProductsData()

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">{t("dashboard.title")}</h1>
        <p className="text-muted-foreground text-sm mt-1">{t("dashboard.subtitle")}</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard title={t("dashboard.totalProducts")} value={stats.total} icon={Package} to="/products" />
        <StatCard title={t("dashboard.scheduled")} value={stats.scheduled} icon={CalendarClock} to="/scheduled" />
        <StatCard title={t("dashboard.published")} value={stats.published} icon={CheckCircle2} to="/published" />
        <StatCard title={t("dashboard.duplicates")} value={stats.duplicate} icon={Copy} to="/duplicates" />
        <StatCard title={t("dashboard.failed")} value={stats.failed} icon={AlertTriangle} to="/failed" />
        <StatCard title={t("dashboard.missing")} value={stats.missing ?? 0} icon={FileWarning} to="/missing" />
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="text-base">{t("dashboard.quickStart")}</CardTitle>
          <CardDescription>{t("dashboard.quickStartDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <ol className="text-sm text-muted-foreground space-y-2 list-decimal list-inside">
            <li>{t("dashboard.step1")}</li>
            <li>{t("dashboard.step2")}</li>
            <li>{t("dashboard.step3")}</li>
            <li>{t("dashboard.step4")}</li>
          </ol>
          <Button asChild className="w-full sm:w-auto bg-[#1877F2] hover:bg-[#166FE5]">
            <Link to="/products">{t("dashboard.goProducts")}</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
