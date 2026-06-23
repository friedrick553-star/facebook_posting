import { useCallback, useEffect, useRef, useState } from "react"
import { Link, Navigate, useSearchParams } from "react-router-dom"
import { Upload, Search, Trash2, Save, Package } from "lucide-react"
import {
  getProducts, uploadProductsCsv, updateProduct, deleteProduct, deleteProducts,
} from "@/lib/api"
import { getUploadToastMessage } from "@/lib/uploadToast"
import type { PaginatedResponse, ProductPost } from "@/types"
import { useProductsData } from "@/contexts/ProductsDataContext"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useToast } from "@/contexts/ToastContext"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge, Spinner } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import ProductImage from "@/components/products/ProductImage"

const SCHEDULE_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const

const STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "destructive" | "secondary"> = {
  pending: "secondary",
  scheduled: "default",
  publishing: "default",
  published: "success",
  failed: "destructive",
  duplicate: "warning",
  missing: "destructive",
}

function formatPrice(price: number | null, currency: string) {
  if (price == null) return "—"
  return `${currency} ${price.toLocaleString()}`
}

function formatDetails(details?: Record<string, string> | null) {
  if (!details || Object.keys(details).length === 0) return "—"
  return Object.entries(details).map(([k, v]) => `${k}: ${v}`).join(" · ")
}

function formatCondition(value: string | undefined, t: (key: string) => string) {
  if (!value) return "—"
  const key = value.toLowerCase()
  if (key === "new" || key === "used") return t(`products.condition.${key}`)
  return value
}

function formatAvailability(value: string | undefined, t: (key: string) => string) {
  if (!value) return "—"
  const key = value.toLowerCase()
  if (key === "single" || key === "stock") return t(`products.availability.${key}`)
  return value
}

const STATUS_REDIRECT: Record<string, string> = {
  scheduled: "/scheduled",
  published: "/published",
  pending: "/pending",
  failed: "/failed",
  duplicate: "/duplicates",
  missing: "/missing",
}

export default function ProductsPage() {
  const [searchParams] = useSearchParams()
  const statusFromUrl = searchParams.get("status") || ""
  if (statusFromUrl && STATUS_REDIRECT[statusFromUrl]) {
    return <Navigate to={STATUS_REDIRECT[statusFromUrl]} replace />
  }
  return <ProductsPageContent />
}

function ProductsPageContent() {
  const { t } = useLanguage()
  const { isAdmin } = useAuth()
  const { toast } = useToast()
  const { refreshStats } = useProductsData()
  const fileRef = useRef<HTMLInputElement>(null)

  const [products, setProducts] = useState<ProductPost[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [drafts, setDrafts] = useState<Record<number, { schedule_day: string; schedule_time: string }>>({})

  const applyList = (data: PaginatedResponse<ProductPost>) => {
    setProducts(data.items)
    setTotal(data.total)
    setSelected(new Set())
    const nextDrafts: Record<number, { schedule_day: string; schedule_time: string }> = {}
    for (const p of data.items) {
      nextDrafts[p.id] = {
        schedule_day: p.schedule_day && SCHEDULE_DAYS.includes(p.schedule_day as typeof SCHEDULE_DAYS[number])
          ? p.schedule_day
          : "mon",
        schedule_time: p.schedule_time || "",
      }
    }
    setDrafts(nextDrafts)
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await getProducts({
        page,
        page_size: 20,
        search: search || undefined,
        catalog: true,
      })
      applyList(data)
    } catch {
      /* keep current list */
    } finally {
      setLoading(false)
    }
  }, [page, search])

  useEffect(() => { load() }, [load])

  const handleSaveSchedule = async (product: ProductPost) => {
    const draft = drafts[product.id]
    if (!draft) return
    if (!draft.schedule_day || !draft.schedule_time) {
      toast(t("products.dayTimeRequired"), "warning")
      return
    }
    setSavingId(product.id)
    try {
      const { data: updated } = await updateProduct(product.id, {
        schedule_day: draft.schedule_day,
        schedule_time: draft.schedule_time,
      })
      setProducts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
      setDrafts((d) => ({
        ...d,
        [updated.id]: {
          schedule_day: updated.schedule_day || draft.schedule_day,
          schedule_time: updated.schedule_time || draft.schedule_time,
        },
      }))
      await refreshStats()
      toast(t("products.scheduleSaved"), "success")
    } catch {
      toast(t("products.scheduleSaveFailed"), "error")
    } finally {
      setSavingId(null)
    }
  }

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      const { data } = await uploadProductsCsv(file)
      const { message, type } = getUploadToastMessage(data, t)
      toast(message, type)
      if (data.parse_warnings?.length) {
        toast(data.parse_warnings.join("; "), "warning")
      }
      await refreshStats()
      setPage(1)
      await load()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || t("products.uploadFailed")
      toast(typeof msg === "string" ? msg : t("products.uploadFailed"), "error")
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm(t("products.deleteConfirm"))) return
    try {
      await deleteProduct(id)
      await refreshStats()
      toast(t("products.deleted"), "success")
      await load()
    } catch {
      toast(t("products.deleteFailed"), "error")
    }
  }

  const handleDeleteSelected = async () => {
    if (selected.size === 0) return
    if (!confirm(t("products.deleteSelectedConfirm", { count: selected.size }))) return
    try {
      await deleteProducts([...selected])
      await refreshStats()
      toast(t("products.deleted"), "success")
      await load()
    } catch {
      toast(t("products.deleteFailed"), "error")
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / 20))

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">{t("products.title")}</h1>
        <p className="text-muted-foreground text-sm mt-1">{t("products.subtitle")}</p>
      </div>

      {isAdmin && (
      <Card className="border-dashed border-2 border-[#1877F2]/30 bg-[#1877F2]/5">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Upload className="h-5 w-5 text-[#1877F2]" />
            {t("products.uploadTitle")}
          </CardTitle>
          <CardDescription>{t("products.uploadDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            {t("products.csvShortHint")}{" "}
            <Link to="/requirements" className="text-primary font-medium hover:underline">
              {t("products.seeRequirements")}
            </Link>
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleUpload(f)
              }}
            />
            <Button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="gap-2 bg-[#1877F2] hover:bg-[#166FE5]"
            >
              {uploading ? <Spinner className="h-4 w-4" /> : <Upload className="h-4 w-4" />}
              {t("products.chooseCsv")}
            </Button>
            <p className="text-xs text-muted-foreground self-center">{t("products.csvHint")}</p>
          </div>
        </CardContent>
      </Card>
      )}

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder={t("products.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (setPage(1), load())}
          />
        </div>
        <Button variant="secondary" onClick={() => { setPage(1); load() }}>{t("common.search")}</Button>
      </div>

      {isAdmin && selected.size > 0 && (
        <div className="flex items-center gap-2">
          <Button variant="destructive" size="sm" onClick={handleDeleteSelected} className="gap-2">
            <Trash2 className="h-4 w-4" />
            {t("common.deleteSelected")} ({selected.size})
          </Button>
        </div>
      )}

      {loading && products.length === 0 ? (
        <div className="flex justify-center py-12"><Spinner className="h-6 w-6" /></div>
      ) : products.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <Package className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="font-semibold text-lg">{t("products.emptyTitle")}</h3>
            <p className="text-sm text-muted-foreground mt-1">{t("products.emptyDesc")}</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="w-full overflow-x-auto rounded-xl border border-border">
            <table className="text-sm min-w-[1400px] w-max">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  {isAdmin && (
                  <th className="p-3 w-10 sticky left-0 z-10 bg-muted/50">
                    <input
                      type="checkbox"
                      checked={selected.size === products.length && products.length > 0}
                      onChange={() => {
                        if (selected.size === products.length) setSelected(new Set())
                        else setSelected(new Set(products.map((p) => p.id)))
                      }}
                      className="h-4 w-4 rounded accent-primary"
                    />
                  </th>
                  )}
                  <th className="p-3 text-left font-medium w-16 whitespace-nowrap">{t("products.col.image")}</th>
                  <th className="p-3 text-left font-medium min-w-[140px] whitespace-nowrap">{t("products.col.name")}</th>
                  <th className="p-3 text-left font-medium min-w-[220px] whitespace-nowrap">{t("products.col.description")}</th>
                  <th className="p-3 text-left font-medium min-w-[90px] whitespace-nowrap">{t("products.col.price")}</th>
                  <th className="p-3 text-left font-medium min-w-[120px] whitespace-nowrap">{t("products.col.category")}</th>
                  <th className="p-3 text-left font-medium min-w-[90px] whitespace-nowrap">{t("products.col.condition")}</th>
                  <th className="p-3 text-left font-medium min-w-[110px] whitespace-nowrap">{t("products.col.availability")}</th>
                  <th className="p-3 text-left font-medium min-w-[240px] whitespace-nowrap">{t("products.col.details")}</th>
                  <th className="p-3 text-left font-medium min-w-[200px] whitespace-nowrap">{t("products.col.images")}</th>
                  <th className="p-3 text-left font-medium min-w-[130px] whitespace-nowrap">{t("products.col.day")}</th>
                  <th className="p-3 text-left font-medium min-w-[110px] whitespace-nowrap">{t("products.col.time")}</th>
                  <th className="p-3 text-left font-medium min-w-[100px] whitespace-nowrap">{t("common.status")}</th>
                  {isAdmin && <th className="p-3 text-left font-medium min-w-[90px] whitespace-nowrap">{t("common.actions")}</th>}
                </tr>
              </thead>
              <tbody>
                {products.map((p) => {
                  const draft = drafts[p.id] || { schedule_day: "mon", schedule_time: "" }
                  const savedDay = p.schedule_day && SCHEDULE_DAYS.includes(p.schedule_day as typeof SCHEDULE_DAYS[number])
                    ? p.schedule_day
                    : "mon"
                  const dirty =
                    draft.schedule_day !== savedDay ||
                    draft.schedule_time !== (p.schedule_time || "")
                  return (
                    <tr key={p.id} className="border-b border-border hover:bg-muted/20 align-top">
                      {isAdmin && (
                      <td className="p-3">
                        <input
                          type="checkbox"
                          checked={selected.has(p.id)}
                          onChange={() => {
                            setSelected((prev) => {
                              const next = new Set(prev)
                              if (next.has(p.id)) next.delete(p.id)
                              else next.add(p.id)
                              return next
                            })
                          }}
                          className="h-4 w-4 rounded accent-primary"
                        />
                      </td>
                      )}
                      <td className="p-3">
                        <ProductImage src={p.images[0]} alt={p.name} />
                      </td>
                      <td className="p-3 font-medium whitespace-nowrap">{p.name}</td>
                      <td className="p-3 text-muted-foreground min-w-[220px] max-w-[320px]">
                        <p className="whitespace-normal">{p.description || "—"}</p>
                      </td>
                      <td className="p-3 tabular-nums whitespace-nowrap">{formatPrice(p.price, p.currency)}</td>
                      <td className="p-3 whitespace-nowrap">{p.category || "—"}</td>
                      <td className="p-3 whitespace-nowrap">{formatCondition(p.condition, t)}</td>
                      <td className="p-3 whitespace-nowrap">{formatAvailability(p.availability, t)}</td>
                      <td className="p-3 text-muted-foreground min-w-[240px] max-w-[360px]">
                        <p className="whitespace-normal text-xs">{formatDetails(p.extra_details)}</p>
                      </td>
                      <td className="p-3 min-w-[200px]">
                        {p.images.length === 0 ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          <div className="space-y-1">
                            <p className="text-xs text-muted-foreground whitespace-nowrap">
                              {t("products.imageCount", { count: p.images.length })}
                            </p>
                            {p.images.map((url, i) => (
                              <a
                                key={`${p.id}-img-${i}`}
                                href={url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="block text-[11px] text-primary hover:underline truncate max-w-[280px]"
                                title={url}
                              >
                                {url}
                              </a>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="p-3">
                        {isAdmin ? (
                        <select
                          className="h-9 w-full rounded-md border border-input bg-card px-2 text-xs"
                          value={draft.schedule_day}
                          onChange={(e) =>
                            setDrafts((d) => ({
                              ...d,
                              [p.id]: { ...draft, schedule_day: e.target.value },
                            }))
                          }
                        >
                          {SCHEDULE_DAYS.map((day) => (
                            <option key={day} value={day}>{t(`products.days.${day}`)}</option>
                          ))}
                        </select>
                        ) : (
                          <span className="text-xs">{p.schedule_day ? t(`products.days.${p.schedule_day}`) : "—"}</span>
                        )}
                      </td>
                      <td className="p-3">
                        {isAdmin ? (
                        <Input
                          type="time"
                          className="h-9 text-xs"
                          value={draft.schedule_time}
                          onChange={(e) =>
                            setDrafts((d) => ({
                              ...d,
                              [p.id]: { ...draft, schedule_time: e.target.value },
                            }))
                          }
                        />
                        ) : (
                          <span className="text-xs">{p.schedule_time || "—"}</span>
                        )}
                      </td>
                      <td className="p-3">
                        <Badge variant={STATUS_VARIANT[p.status] || "secondary"}>
                          {t(`products.status.${p.status}`) || p.status}
                        </Badge>
                      </td>
                      {isAdmin && (
                      <td className="p-3 whitespace-nowrap">
                        <div className="flex gap-1">
                          <Button
                            variant={dirty ? "default" : "ghost"}
                            size="icon"
                            className={cn("h-8 w-8", dirty && "bg-[#1877F2] hover:bg-[#166FE5]")}
                            disabled={!dirty || savingId === p.id}
                            onClick={() => handleSaveSchedule(p)}
                            title={t("products.saveSchedule")}
                          >
                            {savingId === p.id ? <Spinner className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive"
                            onClick={() => handleDelete(p.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                ←
              </Button>
              <span className="text-sm text-muted-foreground">{page} / {totalPages} ({total})</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                →
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
