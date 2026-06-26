import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom"
import { AuthProvider } from "@/contexts/AuthContext"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { ToastProvider } from "@/contexts/ToastContext"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { MonitoringProvider } from "@/contexts/MonitoringContext"
import { ProductsDataProvider } from "@/contexts/ProductsDataContext"
import ProtectedRoute, { AdminRoute, MainAdminRoute } from "@/components/layout/ProtectedRoute"
import LoginPage from "@/pages/LoginPage"
import SetupPage from "@/pages/SetupPage"
import DashboardLayout from "@/components/layout/DashboardLayout"
import DashboardPage from "@/pages/DashboardPage"
import ProductsPage from "@/pages/ProductsPage"
import ProductStatusPage from "@/pages/ProductStatusPage"
import LogsPage from "@/pages/LogsPage"
import SettingsPage from "@/pages/SettingsPage"
import UsersPage from "@/pages/UsersPage"
import RequirementsPage from "@/pages/RequirementsPage"
import { Spinner } from "@/components/ui/badge"
import { SetupProvider, useSetup } from "@/contexts/SetupContext"

function AppRoutes() {
  const location = useLocation()
  const { setupState } = useSetup()

  if (setupState === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="h-8 w-8" />
      </div>
    )
  }

  if (setupState === "needs" && location.pathname !== "/setup") {
    return <Navigate to="/setup" replace />
  }
  if (setupState === "done" && location.pathname === "/setup") {
    return <Navigate to="/login" replace />
  }

  return (
    <Routes>
      <Route path="/setup" element={<SetupPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={
        <ProtectedRoute>
          <MonitoringProvider>
            <ProductsDataProvider>
              <DashboardLayout />
            </ProductsDataProvider>
          </MonitoringProvider>
        </ProtectedRoute>
      }>
        <Route index element={<DashboardPage />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="scheduled" element={<ProductStatusPage kind="scheduled" />} />
        <Route path="published" element={<ProductStatusPage kind="published" />} />
        <Route path="pending" element={<ProductStatusPage kind="pending" />} />
        <Route path="failed" element={<ProductStatusPage kind="failed" />} />
        <Route path="missed" element={<Navigate to="/failed" replace />} />
        <Route path="duplicates" element={<ProductStatusPage kind="duplicate" />} />
        <Route path="missing" element={<ProductStatusPage kind="missing" />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="settings" element={<AdminRoute><SettingsPage /></AdminRoute>} />
        <Route path="requirements" element={<AdminRoute><RequirementsPage /></AdminRoute>} />
        <Route path="users" element={<MainAdminRoute><UsersPage /></MainAdminRoute>} />
        <Route path="filters" element={<Navigate to="/products" replace />} />
        <Route path="listings" element={<Navigate to="/products" replace />} />
        <Route path="listings/*" element={<Navigate to="/products" replace />} />
        <Route path="monitoring" element={<Navigate to="/" replace />} />
        <Route path="notifications" element={<Navigate to="/products" replace />} />
        <Route path="help" element={<Navigate to="/requirements" replace />} />
      </Route>
      <Route path="*" element={<Navigate to={setupState === "needs" ? "/setup" : "/"} replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <LanguageProvider>
        <ThemeProvider>
          <ToastProvider>
            <AuthProvider>
              <SetupProvider>
                <AppRoutes />
              </SetupProvider>
            </AuthProvider>
          </ToastProvider>
        </ThemeProvider>
      </LanguageProvider>
    </BrowserRouter>
  )
}
