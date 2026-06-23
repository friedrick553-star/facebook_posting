import axios from "axios"
import type { User } from "@/types"

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
  timeout: 12000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !error.config?.url?.includes("/auth/login") && !error.config?.url?.includes("/auth/setup")) {
      localStorage.removeItem("token")
      if (!window.location.pathname.startsWith("/login") && !window.location.pathname.startsWith("/setup")) {
        window.location.href = "/login"
      }
    }
    return Promise.reject(error)
  }
)

export default api

export async function checkBackendHealth(): Promise<{ ok: boolean; status: string; database: string; ready?: boolean }> {
  try {
    const res = await axios.get("/health", { timeout: 5000 })
    const status = res.data?.status ?? "unknown"
    const database = res.data?.database ?? "unknown"
    const ready = Boolean(res.data?.ready)
    return {
      ok: ready || status === "healthy",
      status,
      database,
      ready,
    }
  } catch {
    return { ok: false, status: "offline", database: "offline", ready: false }
  }
}

export function loginErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return "Backend not reachable — run start-backend.bat first (port 8001)."
    }
    const detail = error.response.data?.detail
    if (typeof detail === "string") return detail
    if (error.response.status === 503) {
      return "Database still connecting — wait 30 seconds and try again."
    }
    if (error.response.status === 401) {
      return "Invalid email or password"
    }
  }
  return "Login failed — try again."
}

// Auth
export const getSetupStatus = () => api.get<{ needs_setup: boolean }>("/auth/setup-status")
export const completeAdminSetup = (email: string, password: string) =>
  api.post("/auth/setup", { email, password }, { timeout: 20000 })

export const login = (email: string, password: string) =>
  api.post("/auth/login", { email, password }, { timeout: 20000 })

export const getMe = () => api.get("/auth/me")
export const updateProfile = (data: { full_name?: string; email?: string }) =>
  api.put("/auth/profile", data)
export const changePassword = (current_password: string, new_password: string) =>
  api.post("/auth/change-password", { current_password, new_password })

// Dashboard
export const getDashboardStats = () => api.get("/dashboard/stats")
export const getDashboardCharts = () => api.get("/dashboard/charts")

// Monitoring
export const getMonitoringSettings = () => api.get("/monitoring/settings")
export const updateMonitoringSettings = (data: {
  is_enabled?: boolean
  refresh_interval_min_seconds?: number
  refresh_interval_max_seconds?: number
  test_full_flow?: boolean
}) => api.put("/monitoring/settings", data)
export const startBot = () => api.post("/monitoring/start", {}, { timeout: 30000 })
export const stopBot = () => api.post("/monitoring/stop", {}, { timeout: 30000 })

// Filters
export const getFilters = () => api.get("/filters")
export const getFilter = (id: number) => api.get(`/filters/${id}`)
export const createFilter = (data: Record<string, unknown>) => api.post("/filters", data)
export const updateFilter = (id: number, data: Record<string, unknown>) => api.put(`/filters/${id}`, data)
export const deleteFilter = (id: number) => api.delete(`/filters/${id}`)

// Templates
export const getTemplates = () => api.get("/filter-templates")
export const createTemplate = (name: string, filter_data: Record<string, unknown>) =>
  api.post("/filter-templates", { name, filter_data })
export const loadTemplate = (id: number) => api.post(`/filter-templates/${id}/load`)
export const duplicateTemplate = (id: number) => api.post(`/filter-templates/${id}/duplicate`)
export const deleteTemplate = (id: number) => api.delete(`/filter-templates/${id}`)

// Listings
export const getListings = (params: Record<string, unknown>) => api.get("/listings", { params })
export const getListing = (id: number) => api.get(`/listings/${id}`)
export const exportListings = () => api.get("/listings/export/csv", { responseType: "blob" })
export const deleteListings = (ids: number[]) => api.delete("/listings", { data: { ids } })
export const deleteAllListings = () => api.delete("/listings/all")

// Notifications
export const getNotifications = (params: Record<string, unknown>) => api.get("/notifications", { params })
export const getRecipients = () => api.get("/notification-recipients")
export const addRecipient = (data: { email: string; name?: string; is_active?: boolean }) =>
  api.post("/notification-recipients", data)
export const updateRecipient = (id: number, data: { email: string; name?: string; is_active?: boolean }) =>
  api.put(`/notification-recipients/${id}`, data)
export const deleteRecipient = (id: number) => api.delete(`/notification-recipients/${id}`)
export const sendTestEmail = (email?: string) =>
  api.post("/notifications/test-email", email ? { email } : {})
export const sendTestLoginReminder = () => api.post("/notifications/test-login-reminder")

export const getFacebookSessionStatus = () => api.get<{ has_session: boolean; cookie_count: number }>("/settings/facebook-session")
export const importFacebookCookies = (cookies: string) =>
  api.post("/settings/facebook-session", { cookies })

export const getUsers = () => api.get<User[]>("/users/")
export const createUser = (data: { email: string; password: string; full_name: string; role: string }) =>
  api.post("/users/", data)
export const updateUser = (id: number, data: Partial<{ email: string; full_name: string; role: string; is_active: boolean; password: string }>) =>
  api.put(`/users/${id}`, data)
export const deleteUser = (id: number) => api.delete(`/users/${id}`)

export const retryProduct = (id: number) => api.post(`/products/${id}/retry`)

// Settings & Logs
export const getSettings = () => api.get("/settings")
export const updateSettings = (settings: Record<string, string>) => api.put("/settings", { settings })
export const clearBrowserSession = () => api.post("/settings/clear-browser-session")
export const getLogs = (params: Record<string, unknown>) => api.get("/logs", { params })
export const exportLogs = () => api.get("/logs/export/csv", { responseType: "blob" })
export const deleteLogs = (ids: number[]) => api.delete("/logs", { data: { ids } })
export const deleteAllLogs = () => api.delete("/logs/all")

// Products (CSV posting)
export const getProductStats = () => api.get("/products/stats")
export const getProducts = (params: Record<string, unknown>) => api.get("/products", { params })
export const uploadProductsCsv = (file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post("/products/upload-csv", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  })
}
export const updateProduct = (id: number, data: Record<string, unknown>) => api.put(`/products/${id}`, data)
export const deleteProduct = (id: number) => api.delete(`/products/${id}`)
export const deleteProducts = (ids: number[]) => api.delete("/products", { data: { ids } })
