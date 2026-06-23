import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Mail, Settings } from "lucide-react"
import { getNotifications } from "@/lib/api"
import type { Notification } from "@/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge, Spinner, EmptyState } from "@/components/ui/badge"
import { formatDate } from "@/lib/utils"
import { useLanguage } from "@/contexts/LanguageContext"

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const { language, t } = useLanguage()

  useEffect(() => {
    setLoading(true)
    getNotifications({ page, page_size: 20 })
      .then(({ data }) => {
        setNotifications(data.items)
        setTotal(data.total)
      })
      .finally(() => setLoading(false))
  }, [page])

  const totalPages = Math.ceil(total / 20)

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{t("notifications.title")}</h1>
          <p className="text-muted-foreground text-sm mt-1">{t("notifications.subtitle")}</p>
        </div>
        <Button variant="outline" asChild>
          <Link to="/settings">
            <Settings className="h-4 w-4" /> {t("notifications.manageEmails")}
          </Link>
        </Button>
      </div>

      <Card>
        <CardHeader><CardTitle>{t("notifications.history")}</CardTitle></CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-10"><Spinner className="h-8 w-8" /></div>
          ) : notifications.length === 0 ? (
            <EmptyState
              icon={Mail}
              title={t("notifications.emptyTitle")}
              description={t("notifications.emptyDesc")}
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="p-3 text-left font-medium">{t("common.vehicle")}</th>
                      <th className="p-3 text-left font-medium">{t("notifications.recipient")}</th>
                      <th className="p-3 text-left font-medium">{t("notifications.sentAt")}</th>
                      <th className="p-3 text-left font-medium">{t("common.status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notifications.map((n) => (
                      <tr key={n.id} className="border-b border-border hover:bg-muted/30">
                        <td className="p-3">{n.listing_title || `#${n.listing_id}`}</td>
                        <td className="p-3">{n.recipient_email}</td>
                        <td className="p-3">{n.sent_at ? formatDate(n.sent_at, language) : "—"}</td>
                        <td className="p-3"><Badge variant={n.status === "sent" ? "success" : "destructive"}>{n.status}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 && (
                <div className="flex justify-center gap-2 mt-4">
                  <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>←</Button>
                  <span className="text-sm self-center">{page} / {totalPages}</span>
                  <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>→</Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
