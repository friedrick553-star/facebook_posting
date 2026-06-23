import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { getMe, login as apiLogin } from "@/lib/api"
import type { User } from "@/types"

interface AuthContextType {
  user: User | null
  loading: boolean
  isAdmin: boolean
  isMainAdmin: boolean
  isCoAdmin: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = async () => {
    try {
      const { data } = await getMe()
      setUser(data)
    } catch {
      setUser(null)
      localStorage.removeItem("token")
    }
  }

  useEffect(() => {
    const token = localStorage.getItem("token")
    if (token) {
      refreshUser().finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (email: string, password: string) => {
    const { data } = await apiLogin(email, password)
    localStorage.setItem("token", data.access_token)
    await refreshUser()
  }

  const logout = () => {
    localStorage.removeItem("token")
    setUser(null)
  }

  const isMainAdmin = user?.role === "admin" && user?.is_primary === true
  const isOperator = user?.role === "admin" || user?.role === "user"
  const isAdmin = isOperator

  return (
    <AuthContext.Provider value={{ user, loading, isAdmin, isMainAdmin, isCoAdmin: false, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within AuthProvider")
  return context
}
