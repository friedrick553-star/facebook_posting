import axios from "axios"
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react"
import { getMonitoringSettings, startBot, stopBot, getDashboardStats } from "@/lib/api"
import type { MonitoringSettings, DashboardStats } from "@/types"
import { useToast } from "@/contexts/ToastContext"
import { useLanguage } from "@/contexts/LanguageContext"

interface MonitoringContextType {
  settings: MonitoringSettings | null
  stats: DashboardStats | null
  loading: boolean
  toggling: boolean
  startMonitoring: () => Promise<void>
  stopMonitoring: () => Promise<void>
  refresh: () => Promise<void>
}

const MonitoringContext = createContext<MonitoringContextType | undefined>(undefined)

export function MonitoringProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<MonitoringSettings | null>(null)
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [toggling, setToggling] = useState(false)
  const { toast } = useToast()
  const { t } = useLanguage()

  const refresh = useCallback(async () => {
    try {
      const [settingsRes, statsRes] = await Promise.all([
        getMonitoringSettings(),
        getDashboardStats(),
      ])
      setSettings(settingsRes.data)
      setStats(statsRes.data)
    } catch {
      /* backend offline — banner shows */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh().catch(() => {})
  }, [refresh])

  useEffect(() => {
    const ms = settings?.is_enabled ? 10000 : 20000
    const interval = setInterval(refresh, ms)
    return () => clearInterval(interval)
  }, [refresh, settings?.is_enabled])

  const startMonitoring = async () => {
    setToggling(true)
    try {
      await startBot()
      toast(t("bot.onChromium"), "success")
      setSettings((prev) => (prev ? { ...prev, is_enabled: true, is_scanning: true } : prev))
      await refresh()
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) && err.response?.data?.detail
        ? String(err.response.data.detail)
        : t("monitoring.startFailed")
      toast(msg, "error")
    } finally {
      setToggling(false)
    }
  }

  const stopMonitoring = async () => {
    setToggling(true)
    try {
      await stopBot()
      toast(t("bot.off"), "info")
      setSettings((prev) => (prev ? { ...prev, is_enabled: false, is_scanning: false } : prev))
      await refresh()
    } catch {
      toast(t("monitoring.stopFailed"), "error")
    } finally {
      setToggling(false)
    }
  }

  return (
    <MonitoringContext.Provider value={{
      settings, stats, loading, toggling,
      startMonitoring, stopMonitoring, refresh,
    }}>
      {children}
    </MonitoringContext.Provider>
  )
}

export function useMonitoring() {
  const ctx = useContext(MonitoringContext)
  if (!ctx) throw new Error("useMonitoring must be used within MonitoringProvider")
  return ctx
}
