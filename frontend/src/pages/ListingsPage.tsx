import { useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { Search, Download, ExternalLink, Car, Trash2 } from "lucide-react"
import { getListings, exportListings, deleteListings, deleteAllListings } from "@/lib/api"
import type { Listing } from "@/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge, Spinner, EmptyState } from "@/components/ui/badge"
import { formatDate, formatPrice, formatMileage } from "@/lib/utils"
import { useToast } from "@/contexts/ToastContext"

const statusColors: Record<string, "default" | "success" | "warning" | "destructive" | "secondary"> = {
  new: "secondary",
  matched: "default",
  notified: "success",
  skipped: "warning",
  duplicate: "destructive",
}

export default function ListingsPage() {
  const [searchParams] = useSearchParams()
  const [listings, setListings] = useState<Listing[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState(searchParams.get("status") || "")
  const [todayFilter, setTodayFilter] = useState(searchParams.get("today") === "1")
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const navigate = useNavigate()
  const { toast } = useToast()

  useEffect(() => {
    setStatus(searchParams.get("status") || "")
    setTodayFilter(searchParams.get("today") === "1")
    setPage(1)
  }, [searchParams])

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await getListings({
        page,
        page_size: 20,
        search: search || undefined,
        status: status || undefined,
        today: todayFilter || undefined,
      })
      setListings(data.items)
      setTotal(data.total)
      setSelected(new Set())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [page, status, todayFilter])

  const handleSearch = () => { setPage(1); load() }

  const toggleOne = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAllOnPage = () => {
    if (selected.size === listings.length && listings.length > 0) {
      setSelected(new Set())
    } else {
      setSelected(new Set(listings.map((l) => l.id)))
    }
  }

  const handleDeleteSelected = async () => {
    if (selected.size === 0) return
    if (!confirm(`Delete ${selected.size} selected listing(s)?`)) return
    setDeleting(true)
    try {
      const { data } = await deleteListings([...selected])
      toast(`Deleted ${data.deleted} listing(s)`, "success")
      await load()
    } catch {
      toast("Failed to delete listings", "error")
    } finally {
      setDeleting(false)
    }
  }

  const handleDeleteAll = async () => {
    if (total === 0) return
    if (!confirm(`Delete ALL ${total} listings? This cannot be undone.`)) return
    setDeleting(true)
    try {
      const { data } = await deleteAllListings()
      toast(`Deleted ${data.deleted} listing(s)`, "success")
      setPage(1)
      await load()
    } catch {
      toast("Failed to delete all listings", "error")
    } finally {
      setDeleting(false)
    }
  }

  const handleExport = async () => {
    try {
      const { data } = await exportListings()
      const url = window.URL.createObjectURL(new Blob([data]))
      const a = document.createElement("a")
      a.href = url
      a.download = "listings.csv"
      a.click()
      toast("Export downloaded", "success")
    } catch {
      toast("Export failed", "error")
    }
  }

  const totalPages = Math.ceil(total / 20)
  const allOnPageSelected = listings.length > 0 && selected.size === listings.length

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Listings</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {total} listings
            {todayFilter && " · Today only"}
          </p>
        </div>
        <Button variant="outline" onClick={handleExport}><Download className="h-4 w-4" /> Export CSV</Button>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search listings..." value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSearch()} />
        </div>
        <select
          className="h-10 rounded-md border border-input bg-card px-3 text-sm"
          value={todayFilter ? "today" : status}
          onChange={(e) => {
            const val = e.target.value
            setPage(1)
            if (val === "today") {
              navigate("/listings?today=1")
            } else if (val === "") {
              navigate("/listings")
            } else {
              navigate(`/listings?status=${val}`)
            }
          }}
        >
          <option value="">All matched</option>
          <option value="today">Today only</option>
          <option value="notified">Email sent</option>
        </select>
        <Button onClick={handleSearch}>Search</Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>
      ) : listings.length === 0 ? (
        <EmptyState icon={Car} title="No listings found" description="Listings will appear here once monitoring starts" />
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-border">
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border bg-muted/30">
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={allOnPageSelected}
                  onChange={toggleAllOnPage}
                  className="h-4 w-4 rounded border-input accent-primary cursor-pointer"
                  aria-label="Select all on this page"
                />
                <span className="text-sm text-muted-foreground">
                  Select all on this page ({listings.length} listings)
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {selected.size > 0 && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleDeleteSelected}
                    disabled={deleting}
                  >
                    {deleting ? <Spinner /> : <Trash2 className="h-4 w-4" />}
                    Delete selected ({selected.size})
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive border-destructive/30 hover:bg-destructive/10"
                  onClick={handleDeleteAll}
                  disabled={deleting || total === 0}
                >
                  Delete all
                </Button>
              </div>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="p-3 w-10" />
                  <th className="p-3 text-left font-medium">Image</th>
                  <th className="p-3 text-left font-medium">Vehicle</th>
                  <th className="p-3 text-left font-medium">Price</th>
                  <th className="p-3 text-left font-medium hidden md:table-cell">Mileage</th>
                  <th className="p-3 text-left font-medium hidden lg:table-cell">Year</th>
                  <th className="p-3 text-left font-medium hidden lg:table-cell">Location</th>
                  <th className="p-3 text-left font-medium">Score</th>
                  <th className="p-3 text-left font-medium hidden md:table-cell">Found</th>
                  <th className="p-3 text-left font-medium">Status</th>
                  <th className="p-3 text-left font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {listings.map((l) => (
                  <tr key={l.id} className="border-b border-border hover:bg-muted/30 transition-colors">
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={selected.has(l.id)}
                        onChange={() => toggleOne(l.id)}
                        className="h-4 w-4 rounded border-input accent-primary cursor-pointer"
                        aria-label={`Select listing ${l.id}`}
                      />
                    </td>
                    <td className="p-3">
                      {l.images?.[0] ? (
                        <img src={l.images[0]} alt="" className="h-10 w-14 rounded object-cover" />
                      ) : (
                        <div className="h-10 w-14 rounded bg-muted flex items-center justify-center"><Car className="h-4 w-4 text-muted-foreground" /></div>
                      )}
                    </td>
                    <td className="p-3 font-medium max-w-[200px] truncate">{l.title}</td>
                    <td className="p-3">{formatPrice(l.price, l.currency)}</td>
                    <td className="p-3 hidden md:table-cell">{formatMileage(l.mileage)}</td>
                    <td className="p-3 hidden lg:table-cell">{l.year || "—"}</td>
                    <td className="p-3 hidden lg:table-cell max-w-[120px] truncate">{l.location || "—"}</td>
                    <td className="p-3"><Badge variant={l.match_score >= 80 ? "success" : l.match_score >= 50 ? "warning" : "secondary"}>{l.match_score}%</Badge></td>
                    <td className="p-3 hidden md:table-cell text-muted-foreground">{formatDate(l.found_at)}</td>
                    <td className="p-3"><Badge variant={statusColors[l.status] || "secondary"}>{l.status}</Badge></td>
                    <td className="p-3">
                      <Button variant="ghost" size="icon" onClick={() => navigate(`/listings/${l.id}`)}><ExternalLink className="h-4 w-4" /></Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span className="text-sm text-muted-foreground">Page {page} of {totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
