import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { ArrowLeft, ExternalLink, Package, RefreshCw, Save, Search, Trash2 } from "lucide-react"
import { deleteProduct, deleteProducts, getProducts, retryProduct, updateProduct } from "@/lib/api"
import { useAuth } from "@/contexts/AuthContext"
import type { PaginatedResponse, ProductPost } from "@/types"
import { useProductsData } from "@/contexts/ProductsDataContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useToast } from "@/contexts/ToastContext"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { Badge, Spinner } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import ProductImage from "@/components/products/ProductImage"
import { formatScheduleDisplay, normalizeScheduleDate, todayIsoDate } from "@/lib/schedule"
import { formatAppDateTime } from "@/lib/datetime"

export type ProductStatusKind = "scheduled" | "published" | "pending" | "failed" | "duplicate" | "missing"

const PAGE_CONFIG: Record<ProductStatusKind, {
  status: string
  sort: string
  titleKey: string
  subtitleKey: string
  emptyTitleKey: string
  emptyDescKey: string
  showSchedule: boolean
  showPublishedAt: boolean
  showFacebookUrl: boolean
  showError: boolean
  editableSchedule: boolean
}> = {
  scheduled: {
    status: "scheduled",
    sort: "schedule",
    titleKey: "statusPage.scheduled.title",
    subtitleKey: "statusPage.scheduled.subtitle",
    emptyTitleKey: "statusPage.scheduled.emptyTitle",
    emptyDescKey: "statusPage.scheduled.emptyDesc",
    showSchedule: true,
    showPublishedAt: false,
    showFacebookUrl: false,
    showError: false,
    editableSchedule: true,
  },
  published: {
    status: "published",
    sort: "published",
    titleKey: "statusPage.published.title",
    subtitleKey: "statusPage.published.subtitle",
    emptyTitleKey: "statusPage.published.emptyTitle",
    emptyDescKey: "statusPage.published.emptyDesc",
    showSchedule: false,
    showPublishedAt: true,
    showFacebookUrl: true,
    showError: false,
    editableSchedule: false,
  },
  pending: {
    status: "pending",
    sort: "newest",
    titleKey: "statusPage.pending.title",
    subtitleKey: "statusPage.pending.subtitle",
    emptyTitleKey: "statusPage.pending.emptyTitle",
    emptyDescKey: "statusPage.pending.emptyDesc",
    showSchedule: true,
    showPublishedAt: false,
    showFacebookUrl: false,
    showError: false,
    editableSchedule: true,
  },
  failed: {
    status: "failed",
    sort: "newest",
    titleKey: "statusPage.failed.title",
    subtitleKey: "statusPage.failed.subtitle",
    emptyTitleKey: "statusPage.failed.emptyTitle",
    emptyDescKey: "statusPage.failed.emptyDesc",
    showSchedule: true,
    showPublishedAt: false,
    showFacebookUrl: false,
    showError: true,
    editableSchedule: true,
  },
  duplicate: {
    status: "duplicate",
    sort: "newest",
    titleKey: "statusPage.duplicates.title",
    subtitleKey: "statusPage.duplicates.subtitle",
    emptyTitleKey: "statusPage.duplicates.emptyTitle",
    emptyDescKey: "statusPage.duplicates.emptyDesc",
    showSchedule: true,
    showPublishedAt: false,
    showFacebookUrl: false,
    showError: true,
    editableSchedule: false,
  },
  missing: {
    status: "missing",
    sort: "newest",
    titleKey: "statusPage.missing.title",
    subtitleKey: "statusPage.missing.subtitle",
    emptyTitleKey: "statusPage.missing.emptyTitle",
    emptyDescKey: "statusPage.missing.emptyDesc",
    showSchedule: true,
    showPublishedAt: false,
    showFacebookUrl: false,
    showError: true,
    editableSchedule: false,
  },
}

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

function formatSchedule(date: string | null, time: string | null) {
  return formatScheduleDisplay(date, time)
}

export default function ProductStatusPage({ kind }: { kind: ProductStatusKind }) {
  const config = PAGE_CONFIG[kind]
  const { t, language } = useLanguage()
  const { toast } = useToast()
  const { refreshStats } = useProductsData()
  const { isAdmin } = useAuth()

  const [products, setProducts] = useState<ProductPost[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [loading, setLoading] = useState(false)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [retryingId, setRetryingId] = useState<number | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [drafts, setDrafts] = useState<Record<number, { schedule_date: string; schedule_time: string }>>({})

  const applyList = (data: PaginatedResponse<ProductPost>) => {
    setProducts(data.items)
    setTotal(data.total)
    setSelected(new Set())
    const nextDrafts: Record<number, { schedule_date: string; schedule_time: string }> = {}
    for (const p of data.items) {
      nextDrafts[p.id] = {
        schedule_date: normalizeScheduleDate(p.schedule_date),
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
        status: config.status,
        sort: config.sort,
      })
      applyList(data)
    } catch {
      /* keep current list */
    } finally {
      setLoading(false)
    }
  }, [page, search, config.status, config.sort, kind])

  useEffect(() => { load() }, [load])

  const handleSaveSchedule = async (product: ProductPost) => {
    const draft = drafts[product.id]
    if (!draft) return
    if (!draft.schedule_date || !draft.schedule_time) {
      toast(t("products.dateTimeRequired"), "warning")
      return
    }
    setSavingId(product.id)
    try {
      const { data: updated } = await updateProduct(product.id, {
        schedule_date: draft.schedule_date,
        schedule_time: draft.schedule_time,
      })
      if ((kind === "pending" || kind === "failed") && updated.status === "scheduled") {
        setProducts((prev) => prev.filter((p) => p.id !== updated.id))
        setTotal((n) => Math.max(0, n - 1))
        await refreshStats()
        toast(t("products.scheduleSaved"), "success")
      } else {
        setProducts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
        await refreshStats()
        toast(t("products.scheduleSaved"), "success")
      }
    } catch {
      toast(t("products.scheduleSaveFailed"), "error")
    } finally {
      setSavingId(null)
    }
  }

  const handleRetry = async (id: number) => {
    setRetryingId(id)
    try {
      await retryProduct(id)
      toast(t("products.retryQueued"), "success")
      refreshStats()
      load()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t("products.retryFailed")
      toast(msg, "error")
    } finally {
      setRetryingId(null)
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Button variant="ghost" size="sm" asChild className="mb-2 -ml-2 gap-1 text-muted-foreground">
            <Link to="/">
              <ArrowLeft className="h-4 w-4" />
              {t("statusPage.backDashboard")}
            </Link>
          </Button>
          <h1 className="text-2xl font-bold">{t(config.titleKey)}</h1>
          <p className="text-muted-foreground text-sm mt-1">{t(config.subtitleKey)}</p>
          <p className="text-xs text-muted-foreground mt-1">{total} {t("statusPage.items")}</p>
        </div>
      </div>

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
            <h3 className="font-semibold text-lg">{t(config.emptyTitleKey)}</h3>
            <p className="text-sm text-muted-foreground mt-1">{t(config.emptyDescKey)}</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-sm min-w-[800px]">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="p-3 w-10">
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
                  {kind === "scheduled" && (
                    <th className="p-3 text-left font-medium w-12">#</th>
                  )}
                  <th className="p-3 text-left font-medium w-16">{t("products.col.image")}</th>
                  <th className="p-3 text-left font-medium min-w-[140px]">{t("products.col.name")}</th>
                  <th className="p-3 text-left font-medium min-w-[180px]">{t("products.col.description")}</th>
                  <th className="p-3 text-left font-medium w-24">{t("products.col.price")}</th>
                  {config.showSchedule && !config.editableSchedule && (
                    <th className="p-3 text-left font-medium w-40">{t("statusPage.col.schedule")}</th>
                  )}
                  {config.showSchedule && config.editableSchedule && (
                    <>
                      <th className="p-3 text-left font-medium w-36">{t("products.col.date")}</th>
                      <th className="p-3 text-left font-medium w-28">{t("products.col.time")}</th>
                    </>
                  )}
                  {config.showPublishedAt && (
                    <th className="p-3 text-left font-medium w-40">{t("statusPage.col.publishedAt")}</th>
                  )}
                  {config.showFacebookUrl && (
                    <th className="p-3 text-left font-medium w-24">{t("statusPage.col.link")}</th>
                  )}
                  {config.showError && (
                    <th className="p-3 text-left font-medium min-w-[160px]">{t("statusPage.col.error")}</th>
                  )}
                  <th className="p-3 text-left font-medium w-28">{t("common.status")}</th>
                  <th className="p-3 text-left font-medium w-24">{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p, index) => {
                  const draft = drafts[p.id] || { schedule_date: todayIsoDate(), schedule_time: "" }
                  const savedDate = p.schedule_date || todayIsoDate()
                  const dirty =
                    draft.schedule_date !== savedDate ||
                    draft.schedule_time !== (p.schedule_time || "")

                  return (
                    <tr key={p.id} className="border-b border-border hover:bg-muted/20 align-top">
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
                      {kind === "scheduled" && (
                        <td className="p-3 text-muted-foreground tabular-nums font-medium">
                          {(page - 1) * 20 + index + 1}
                        </td>
                      )}
                      <td className="p-3">
                        <ProductImage src={p.images[0]} alt={p.name} />
                      </td>
                      <td className="p-3 font-medium">{p.name}</td>
                      <td className="p-3 text-muted-foreground max-w-[240px]">
                        <p className="line-clamp-3">{p.description || "—"}</p>
                      </td>
                      <td className="p-3 tabular-nums whitespace-nowrap">{formatPrice(p.price, p.currency)}</td>
                      {config.showSchedule && !config.editableSchedule && (
                        <td className="p-3 whitespace-nowrap">{formatSchedule(p.schedule_date, p.schedule_time)}</td>
                      )}
                      {config.showSchedule && config.editableSchedule && (
                        <>
                          <td className="p-3">
                            <Input
                              type="date"
                              className="h-9 text-xs"
                              value={draft.schedule_date}
                              onChange={(e) =>
                                setDrafts((d) => ({
                                  ...d,
                                  [p.id]: { ...draft, schedule_date: e.target.value },
                                }))
                              }
                            />
                          </td>
                          <td className="p-3">
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
                          </td>
                        </>
                      )}
                      {config.showPublishedAt && (
                        <td className="p-3 whitespace-nowrap text-muted-foreground">
                          {p.published_at ? formatAppDateTime(p.published_at, language) : "—"}
                        </td>
                      )}
                      {config.showFacebookUrl && (
                        <td className="p-3">
                          {p.facebook_url ? (
                            <a
                              href={p.facebook_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[#1877F2] hover:underline text-xs"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                              {t("statusPage.viewPost")}
                            </a>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      )}
                      {config.showError && (
                        <td className="p-3 text-destructive text-xs max-w-[200px]">
                          <p className="line-clamp-3">{p.error_message || "—"}</p>
                        </td>
                      )}
                      <td className="p-3">
                        <div className="flex flex-wrap items-center gap-1">
                          {p.is_queued && (
                            <Badge variant="warning">{t("products.tag.queued")}</Badge>
                          )}
                          <Badge variant={STATUS_VARIANT[p.status] || "secondary"}>
                            {t(`products.status.${p.status}`) || p.status}
                          </Badge>
                        </div>
                      </td>
                      <td className="p-3">
                        {isAdmin ? (
                        <div className="flex gap-1">
                          {kind === "failed" && (
                            <Button
                              variant="outline"
                              size="icon"
                              className="h-8 w-8"
                              disabled={retryingId === p.id}
                              onClick={() => handleRetry(p.id)}
                              title={t("common.retry")}
                            >
                              {retryingId === p.id ? <Spinner className="h-3.5 w-3.5" /> : <RefreshCw className="h-3.5 w-3.5" />}
                            </Button>
                          )}
                          {config.editableSchedule && (
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
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive"
                            onClick={() => handleDelete(p.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
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
