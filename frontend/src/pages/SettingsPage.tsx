import { useEffect, useState } from "react"
import { Cookie, Eraser, FlaskConical, Monitor } from "lucide-react"
import {
  clearBrowserSession,
  getFacebookSessionStatus,
  getMonitoringSettings,
  importFacebookCookies,
  updateMonitoringSettings,
} from "@/lib/api"
import { useToast } from "@/contexts/ToastContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { Button } from "@/components/ui/button"
import { Input, Label } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge, Spinner } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [clearingSession, setClearingSession] = useState(false)
  const [cookieText, setCookieText] = useState("")
  const [importingCookies, setImportingCookies] = useState(false)
  const [testFullFlow, setTestFullFlow] = useState(false)
  const [savingTestFlow, setSavingTestFlow] = useState(false)
  const [fbSession, setFbSession] = useState<{ has_session: boolean; cookie_count: number } | null>(null)
  const { toast } = useToast()
  const { t } = useLanguage()

  const load = async () => {
    const [sessionRes, settingsRes] = await Promise.all([
      getFacebookSessionStatus(),
      getMonitoringSettings(),
    ])
    setFbSession(sessionRes.data)
    setTestFullFlow(Boolean(settingsRes.data?.test_full_flow))
    setLoading(false)
  }

  useEffect(() => {
    load()
  }, [])

  const handleImportCookies = async () => {
    if (!cookieText.trim()) return
    setImportingCookies(true)
    try {
      await importFacebookCookies(cookieText.trim())
      setCookieText("")
      toast(t("settings.cookiesSaved"), "success")
      const { data } = await getFacebookSessionStatus()
      setFbSession(data)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t("settings.cookiesFailed")
      toast(msg, "error")
    } finally {
      setImportingCookies(false)
    }
  }

  const handleSaveTestFullFlow = async (checked: boolean) => {
    setTestFullFlow(checked)
    setSavingTestFlow(true)
    try {
      await updateMonitoringSettings({ test_full_flow: checked })
      toast(t("settings.testFullFlowSaved"), "success")
    } catch (err: unknown) {
      setTestFullFlow(!checked)
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t("settings.saveFailed")
      toast(typeof msg === "string" ? msg : t("settings.saveFailed"), "error")
    } finally {
      setSavingTestFlow(false)
    }
  }

  const handleClearBrowserSession = async () => {
    if (!confirm(t("settings.clearBrowserConfirm"))) return
    setClearingSession(true)
    try {
      await clearBrowserSession()
      toast(t("settings.sessionCleared"), "success")
      setFbSession({ has_session: false, cookie_count: 0 })
    } catch {
      toast(t("settings.sessionClearFailed"), "error")
    } finally {
      setClearingSession(false)
    }
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold">{t("settings.title")}</h1>
        <p className="text-muted-foreground text-sm mt-1">{t("settings.subtitle")}</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Cookie className="h-5 w-5 text-primary" />
            <CardTitle>{t("settings.facebookCookies")}</CardTitle>
          </div>
          <CardDescription>{t("settings.facebookCookiesDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-4 rounded-lg border border-border bg-muted/30">
            <div>
              <p className="font-medium text-sm">{t("settings.sessionStatus")}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {fbSession?.has_session ? t("settings.sessionActive") : t("settings.sessionMissing")}
              </p>
            </div>
            <Badge variant={fbSession?.has_session ? "success" : "destructive"}>
              {fbSession?.has_session
                ? t("settings.cookiesCount", { count: fbSession.cookie_count })
                : t("settings.sessionMissing")}
            </Badge>
          </div>
          <div className="space-y-2">
            <Label>{t("settings.pasteCookies")}</Label>
            <textarea
              className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
              placeholder={t("settings.cookiesPlaceholder")}
              value={cookieText}
              onChange={(e) => setCookieText(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t("settings.cookiesHint")}</p>
          </div>
          <Button onClick={handleImportCookies} disabled={importingCookies || !cookieText.trim()}>
            {importingCookies ? <Spinner /> : t("settings.saveCookies")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-primary" />
            <CardTitle>{t("settings.testFullFlow")}</CardTitle>
          </div>
          <CardDescription>{t("settings.testFullFlowDesc")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-4 p-4 rounded-lg border border-border bg-muted/30">
            <div className="space-y-1">
              <p className="font-medium text-sm">{t("settings.testFullFlowLabel")}</p>
              <p className="text-xs text-muted-foreground">{t("settings.testFullFlowHint")}</p>
            </div>
            <Switch
              checked={testFullFlow}
              disabled={savingTestFlow}
              onCheckedChange={handleSaveTestFullFlow}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Monitor className="h-5 w-5 text-primary" />
            <CardTitle>{t("settings.browser")}</CardTitle>
          </div>
          <CardDescription>{t("settings.browserDesc")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between p-4 rounded-lg border border-border bg-muted/30">
            <div>
              <p className="font-medium text-sm">{t("settings.clearBrowser")}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{t("settings.clearBrowserDesc")}</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleClearBrowserSession}
              disabled={clearingSession}
            >
              {clearingSession ? <Spinner /> : <><Eraser className="h-4 w-4" /> {t("common.clear")}</>}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
