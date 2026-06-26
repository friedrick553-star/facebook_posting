import { Menu, Moon, Sun, Languages, LogOut } from "lucide-react"
import { useNavigate } from "react-router-dom"
import { useTheme } from "@/contexts/ThemeContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useAuth } from "@/contexts/AuthContext"
import MonitoringControls from "@/components/layout/MonitoringControls"
import ItalyClock from "@/components/layout/ItalyClock"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface AppHeaderProps {
  onMenuClick: () => void
}

export default function AppHeader({ onMenuClick }: AppHeaderProps) {
  const { resolvedTheme, setTheme } = useTheme()
  const { language, toggleLanguage, t } = useLanguage()
  const { user, logout, isAdmin } = useAuth()
  const navigate = useNavigate()

  const toggleTheme = () => setTheme(resolvedTheme === "dark" ? "light" : "dark")

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-card backdrop-blur-md shadow-[0_1px_4px_rgba(15,23,42,0.06)] dark:shadow-[0_1px_0_oklch(0.28_0.03_264),0_4px_16px_rgba(0,0,0,0.45)] dark:bg-card/98">
      <div className="flex items-center gap-2 px-4 py-3 lg:px-6">
        <button
          className="lg:hidden p-2 rounded-lg hover:bg-accent transition-colors"
          onClick={onMenuClick}
          aria-label={t("header.openMenu")}
        >
          <Menu className="h-5 w-5" />
        </button>

        <div className="flex-1" />

        <ItalyClock />

        {isAdmin && <MonitoringControls compact />}

        {user && (
          <span className="hidden md:inline text-xs text-muted-foreground truncate max-w-[140px]">
            {user.full_name}
          </span>
        )}

        <div className="h-6 w-px bg-border mx-1 hidden sm:block" />

        <Button
          variant="ghost"
          size="sm"
          onClick={toggleLanguage}
          title={language === "it" ? t("header.switchToEnglish") : t("header.switchToItalian")}
          className="rounded-lg shrink-0 gap-1.5 px-2.5 h-9 font-semibold"
        >
          <Languages className="h-4 w-4 text-muted-foreground" />
          <span className={cn(
            "text-xs tabular-nums",
            language === "it" ? "text-[#1877F2]" : "text-muted-foreground"
          )}>IT</span>
          <span className="text-muted-foreground/50 text-xs">/</span>
          <span className={cn(
            "text-xs tabular-nums",
            language === "en" ? "text-[#1877F2]" : "text-muted-foreground"
          )}>EN</span>
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          title={resolvedTheme === "dark" ? t("header.lightMode") : t("header.darkMode")}
          className="rounded-lg shrink-0"
        >
          {resolvedTheme === "dark" ? (
            <Sun className="h-5 w-5 text-amber-400" />
          ) : (
            <Moon className="h-5 w-5 text-slate-600" />
          )}
        </Button>

        <Button
          variant="ghost"
          size="icon"
          onClick={handleLogout}
          title={t("login.logout")}
          className="rounded-lg shrink-0"
        >
          <LogOut className="h-5 w-5 text-muted-foreground" />
        </Button>
      </div>
    </header>
  )
}
