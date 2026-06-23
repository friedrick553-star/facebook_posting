import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Eye, EyeOff } from "lucide-react"
import { useToast } from "@/contexts/ToastContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useSetup } from "@/contexts/SetupContext"
import { Logo } from "@/components/brand/Logo"
import { Button } from "@/components/ui/button"
import { Input, Label } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/badge"
import { checkBackendHealth, completeAdminSetup, getSetupStatus } from "@/lib/api"
import { cn } from "@/lib/utils"
import axios from "axios"

export default function SetupPage() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [backendStatus, setBackendStatus] = useState<"checking" | "ready" | "connecting" | "offline">("checking")
  const { toast } = useToast()
  const { t } = useLanguage()
  const { markSetupDone } = useSetup()
  const navigate = useNavigate()

  const passwordsMatch = password === confirmPassword
  const canSubmit =
    backendStatus === "ready" &&
    email.trim() &&
    password.length >= 6 &&
    passwordsMatch

  useEffect(() => {
    let cancelled = false
    let attempts = 0

    const poll = async () => {
      const health = await checkBackendHealth()
      if (cancelled) return

      if (health.ok) {
        try {
          const { data } = await getSetupStatus()
          if (!data.needs_setup) {
            navigate("/login", { replace: true })
            return
          }
        } catch {
          // setup-status may 503 while DB connects — keep polling
        }
        setBackendStatus("ready")
        return
      }
      if (health.status === "starting" || health.database === "connecting") {
        setBackendStatus("connecting")
      } else if (attempts === 0) {
        setBackendStatus("checking")
      } else {
        setBackendStatus(attempts < 25 ? "connecting" : "offline")
      }

      attempts += 1
      if (attempts < 30 && !health.ok) {
        setTimeout(poll, 3000)
      }
    }

    poll()
    return () => {
      cancelled = true
    }
  }, [navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (backendStatus !== "ready") {
      toast(t("login.serverNotReady"), "warning")
      return
    }
    if (!passwordsMatch) {
      toast(t("setup.passwordMismatch"), "error")
      return
    }
    setLoading(true)
    try {
      await completeAdminSetup(email.trim(), password)
      markSetupDone()
      toast(t("setup.success"), "success")
      navigate("/login", { replace: true })
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail
        toast(typeof detail === "string" ? detail : t("setup.failed"), "error")
      } else {
        toast(t("setup.failed"), "error")
      }
    } finally {
      setLoading(false)
    }
  }

  const statusMessage =
    backendStatus === "checking"
      ? t("login.connecting")
      : backendStatus === "connecting"
        ? t("login.starting")
        : backendStatus === "offline"
          ? t("login.offline")
          : t("setup.subtitle")

  return (
    <div className="flex min-h-screen">
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-[#1877F2] to-[#0d5bbd] items-center justify-center p-12">
        <div className="relative text-center text-white max-w-md">
          <img src="/logo.svg" alt="" className="h-24 w-24 rounded-3xl shadow-2xl mx-auto mb-8" />
          <h1 className="text-3xl font-bold mb-3">{t("app.title")}</h1>
          <p className="text-blue-100 text-lg leading-relaxed">{t("setup.hero")}</p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center bg-background p-6">
        <div className="w-full max-w-md animate-fade-in">
          <div className="flex flex-col items-center mb-8 lg:hidden">
            <Logo size={64} className="mb-4 shadow-md" />
            <h1 className="text-2xl font-bold">{t("app.title")}</h1>
          </div>

          <Card className="shadow-lg border-border/60">
            <CardHeader>
              <CardTitle>{t("setup.title")}</CardTitle>
              <CardDescription>{statusMessage}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="setup-email">{t("login.email")}</Label>
                  <Input
                    id="setup-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="setup-password">{t("login.password")}</Label>
                  <div className="relative">
                    <Input
                      id="setup-password"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      minLength={6}
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground">{t("setup.passwordHint")}</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="setup-confirm">{t("setup.confirmPassword")}</Label>
                  <Input
                    id="setup-confirm"
                    type={showPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                  />
                </div>
                <Button
                  type="submit"
                  className={cn(
                    "w-full font-semibold",
                    canSubmit ? "bg-[#1877F2] hover:bg-[#166fe5] text-white" : "bg-muted text-muted-foreground"
                  )}
                  disabled={loading || !canSubmit}
                >
                  {loading ? <Spinner /> : backendStatus !== "ready" ? t("login.waitServer") : t("setup.submit")}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
