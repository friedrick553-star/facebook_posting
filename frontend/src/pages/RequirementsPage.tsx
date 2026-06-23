import { Link } from "react-router-dom"
import { FileSpreadsheet } from "lucide-react"
import { useLanguage } from "@/contexts/LanguageContext"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

export default function RequirementsPage() {
  const { t } = useLanguage()

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold">{t("requirements.title")}</h1>
        <p className="text-muted-foreground text-sm mt-1">{t("requirements.subtitle")}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileSpreadsheet className="h-5 w-5 text-primary" />
            {t("requirements.csvTitle")}
          </CardTitle>
          <CardDescription>{t("requirements.csvDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <div>
            <p className="font-medium text-foreground mb-2">{t("requirements.requiredLabel")}</p>
            <p className="font-mono text-xs bg-muted/60 rounded-md p-3 break-all">
              {t("requirements.columns")}
            </p>
          </div>

          <div>
            <p className="font-medium text-foreground mb-2">{t("requirements.optionalLabel")}</p>
            <p className="font-mono text-xs bg-muted/60 rounded-md p-3 break-all">
              {t("requirements.optionalColumns")}
            </p>
          </div>

          <ul className="space-y-1.5 list-disc pl-5">
            {(t("requirements.rules") as string).split("|").map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>

          <div className="rounded-lg border border-border p-3 space-y-1">
            <p className="font-medium text-foreground text-xs">{t("requirements.imagesLabel")}</p>
            <p className="text-xs">{t("requirements.imagesHint")}</p>
            <p className="font-mono text-[11px] break-all text-muted-foreground">{t("requirements.imagesExample")}</p>
          </div>

          <p className="text-xs">
            {t("requirements.detailsHint")}
          </p>

          <Link to="/products" className="text-primary text-sm font-medium hover:underline">
            {t("requirements.backProducts")}
          </Link>
        </CardContent>
      </Card>
    </div>
  )
}
