import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"
import { useLocation } from "react-router-dom"
import { getProductStats } from "@/lib/api"
import type { ProductStats } from "@/types"

const EMPTY_STATS: ProductStats = {
  total: 0,
  pending: 0,
  scheduled: 0,
  published: 0,
  failed: 0,
  duplicate: 0,
  missing: 0,
}

interface ProductsDataContextType {
  stats: ProductStats
  statsLoading: boolean
  refreshStats: () => Promise<ProductStats | null>
}

const ProductsDataContext = createContext<ProductsDataContextType | undefined>(undefined)

const PRODUCT_ROUTES = new Set(["/", "/products", "/scheduled", "/published", "/pending", "/failed", "/duplicates", "/missing"])

export function ProductsDataProvider({ children }: { children: ReactNode }) {
  const location = useLocation()
  const [stats, setStats] = useState<ProductStats>(EMPTY_STATS)
  const [statsLoading, setStatsLoading] = useState(false)

  const refreshStats = useCallback(async () => {
    setStatsLoading(true)
    try {
      const { data } = await getProductStats()
      setStats(data)
      return data
    } catch {
      return null
    } finally {
      setStatsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (PRODUCT_ROUTES.has(location.pathname)) {
      refreshStats()
    }
  }, [location.pathname, refreshStats])

  return (
    <ProductsDataContext.Provider value={{ stats, statsLoading, refreshStats }}>
      {children}
    </ProductsDataContext.Provider>
  )
}

export function useProductsData() {
  const ctx = useContext(ProductsDataContext)
  if (!ctx) throw new Error("useProductsData must be used within ProductsDataProvider")
  return ctx
}
