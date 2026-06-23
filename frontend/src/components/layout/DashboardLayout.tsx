import { LayoutDashboard, Package, FileText, Settings, Users, FileSpreadsheet, X } from "lucide-react"
import { useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { Logo, BrandTitle } from "@/components/brand/Logo"
import AppHeader from "@/components/layout/AppHeader"
import BackendStatusBanner from "@/components/layout/BackendStatusBanner"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { cn } from "@/lib/utils"

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { t } = useLanguage()
  const { isAdmin, isMainAdmin } = useAuth()

  const navItems = [
    { to: "/", icon: LayoutDashboard, label: t("nav.dashboard") },
    { to: "/products", icon: Package, label: t("nav.products") },
    { to: "/logs", icon: FileText, label: t("nav.logs") },
    ...(isMainAdmin ? [{ to: "/users", icon: Users, label: t("nav.users") }] : []),
    ...(isAdmin ? [
      { to: "/settings", icon: Settings, label: t("nav.settings") },
      { to: "/requirements", icon: FileSpreadsheet, label: t("nav.requirements") },
    ] : []),
  ]

  return (
    <div className="flex min-h-screen bg-background">
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      <aside className={cn(
        "fixed inset-y-0 left-0 z-50 w-64 transform border-r border-border bg-card transition-transform duration-300 lg:translate-x-0 lg:static",
        "shadow-xl lg:shadow-[2px_0_12px_rgba(0,0,0,0.08)] dark:lg:shadow-[2px_0_16px_rgba(0,0,0,0.45)]",
        sidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="flex h-full flex-col">
          <div className="flex items-center gap-3 border-b border-border px-5 py-4 bg-card">
            <Logo size={36} />
            <BrandTitle />
            <button className="ml-auto lg:hidden p-1 rounded-md hover:bg-accent" onClick={() => setSidebarOpen(false)}>
              <X className="h-5 w-5" />
            </button>
          </div>

          <nav className="flex-1 space-y-0.5 p-3 pt-4">
            {navItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) => cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
                  isActive
                    ? "bg-[#1877F2]/10 text-[#1877F2] shadow-sm border border-[#1877F2]/25 font-semibold"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground border border-transparent"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="border-t border-border p-4">
            <div className="rounded-lg bg-gradient-to-br from-[#1877F2]/8 to-emerald-500/5 border border-[#1877F2]/20 p-3 shadow-sm">
              <p className="text-xs font-semibold text-[#1877F2]">{t("app.title")}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{t("app.sidebarTagline")}</p>
            </div>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <AppHeader onMenuClick={() => setSidebarOpen(true)} />
        <main className="flex-1 p-4 lg:p-6 xl:p-8 overflow-auto">
          <BackendStatusBanner />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
