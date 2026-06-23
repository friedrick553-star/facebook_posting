import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { ArrowLeft, ExternalLink, Car } from "lucide-react"
import { getListing, getNotifications } from "@/lib/api"
import type { Listing, Notification } from "@/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge, Spinner } from "@/components/ui/badge"
import { formatDate, formatPrice, formatMileage } from "@/lib/utils"

export default function ListingDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [listing, setListing] = useState<Listing | null>(null)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    Promise.all([
      getListing(Number(id)),
      getNotifications({ page: 1, page_size: 50 }),
    ]).then(([lRes, nRes]) => {
      setListing(lRes.data)
      setNotifications(nRes.data.items.filter((n: Notification) => n.listing_id === Number(id)))
    }).finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>
  if (!listing) return <div className="text-center py-20">Listing not found</div>

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate("/listings")}><ArrowLeft className="h-4 w-4" /></Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{listing.title}</h1>
          <p className="text-muted-foreground text-sm">{listing.location} · Found {formatDate(listing.found_at)}</p>
        </div>
        <Badge variant={listing.match_score >= 80 ? "success" : "warning"}>{listing.match_score}% Match</Badge>
        <Button asChild><a href={listing.url} target="_blank" rel="noopener noreferrer"><ExternalLink className="h-4 w-4" /> View on Facebook</a></Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {listing.images?.length > 0 ? (
            <div className="grid grid-cols-2 gap-2">
              {listing.images.map((img, i) => (
                <img key={i} src={img} alt="" className={`rounded-xl object-cover w-full ${i === 0 ? "col-span-2 h-64" : "h-32"}`} />
              ))}
            </div>
          ) : (
            <Card><CardContent className="flex items-center justify-center h-48"><Car className="h-12 w-12 text-muted-foreground" /></CardContent></Card>
          )}

          {listing.description && (
            <Card>
              <CardHeader><CardTitle>Description</CardTitle></CardHeader>
              <CardContent><p className="text-sm whitespace-pre-wrap">{listing.description}</p></CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Vehicle Details</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex justify-between"><span className="text-muted-foreground">Price</span><span className="font-semibold">{formatPrice(listing.price, listing.currency)}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Mileage</span><span>{formatMileage(listing.mileage)}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Year</span><span>{listing.year || "—"}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Brand</span><span>{listing.brand || "—"}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Model</span><span>{listing.model || "—"}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Fuel</span><span>{listing.fuel_type || "—"}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Transmission</span><span>{listing.transmission || "—"}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Status</span><Badge variant="secondary">{listing.status}</Badge></div>
            </CardContent>
          </Card>

          {listing.match_details && (
            <Card>
              <CardHeader><CardTitle>Matching Analysis</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(listing.match_details).map(([key, score]) => (
                  <div key={key} className="flex items-center gap-3">
                    <span className="text-sm capitalize w-24 text-muted-foreground">{key.replace("_", " ")}</span>
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${score}%` }} />
                    </div>
                    <span className="text-xs font-medium w-10 text-right">{Math.round(score)}%</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader><CardTitle>Notification History</CardTitle></CardHeader>
            <CardContent>
              {notifications.length === 0 ? (
                <p className="text-sm text-muted-foreground">No notifications sent for this listing</p>
              ) : (
                <div className="space-y-2">
                  {notifications.map((n) => (
                    <div key={n.id} className="flex items-center justify-between text-sm p-2 rounded-lg bg-muted/50">
                      <span>{n.recipient_email}</span>
                      <Badge variant={n.status === "sent" ? "success" : "destructive"}>{n.status}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
