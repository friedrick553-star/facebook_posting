import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { interpolate, translations, type Language } from "@/lib/i18n/translations"

const STORAGE_KEY = "fb-posting-language"
const LANG_VERSION = "2"

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  toggleLanguage: () => void
  t: (key: string, params?: Record<string, string | number>) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

function readStoredLanguage(): Language {
  try {
    if (localStorage.getItem("fb-posting-language-version") !== LANG_VERSION) {
      localStorage.setItem("fb-posting-language-version", LANG_VERSION)
      localStorage.setItem(STORAGE_KEY, "it")
      localStorage.removeItem("fb-posting-language-chosen")
      return "it"
    }
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === "en" || stored === "it") return stored
  } catch {
    /* ignore */
  }
  return "it"
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(readStoredLanguage)

  const setLanguage = (lang: Language) => {
    setLanguageState(lang)
    localStorage.setItem(STORAGE_KEY, lang)
    localStorage.setItem("fb-posting-language-version", LANG_VERSION)
  }

  const toggleLanguage = () => {
    setLanguage(language === "it" ? "en" : "it")
  }

  const t = (key: string, params?: Record<string, string | number>) => {
    const text = translations[language][key] ?? translations.en[key] ?? key
    return interpolate(text, params)
  }

  useEffect(() => {
    document.documentElement.lang = language
    document.title = `${translations[language]["app.title"]} — ${translations[language]["app.subtitle"]}`
  }, [language])

  return (
    <LanguageContext.Provider value={{ language, setLanguage, toggleLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (!context) throw new Error("useLanguage must be used within LanguageProvider")
  return context
}
