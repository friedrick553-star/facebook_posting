import { useEffect, useState } from "react"
import { Crown, Plus, Trash2, UserCog } from "lucide-react"
import { createUser, deleteUser, getUsers, updateUser } from "@/lib/api"
import { useToast } from "@/contexts/ToastContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { Button } from "@/components/ui/button"
import { Input, Label } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge, Spinner } from "@/components/ui/badge"
import type { User } from "@/types"

function roleLabel(user: User, t: (key: string) => string): string {
  if (user.is_primary === true) return t("users.roleMainAdmin")
  return t("users.roleUser")
}

export default function UsersPage() {
  const { t } = useLanguage()
  const { toast } = useToast()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
  })

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await getUsers()
      setUsers(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const primaryAdmin = users.find((u) => u.is_primary === true)
  const teamUsers = users.filter((u) => u.is_primary !== true)

  const handleCreate = async () => {
    if (!form.email.trim() || !form.password || !form.full_name.trim()) return
    setSaving(true)
    try {
      await createUser({ ...form, role: "user" })
      setForm({ email: "", password: "", full_name: "" })
      toast(t("users.created"), "success")
      load()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t("users.createFailed")
      toast(msg, "error")
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async (user: User) => {
    if (user.is_primary) return
    try {
      await updateUser(user.id, { is_active: !user.is_active })
      toast(t("users.updated"), "success")
      load()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t("users.updateFailed")
      toast(msg, "error")
    }
  }

  const handleDelete = async (user: User) => {
    if (user.is_primary) return
    if (!confirm(t("users.deleteConfirm", { email: user.email }))) return
    try {
      await deleteUser(user.id)
      toast(t("users.deleted"), "success")
      load()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t("users.deleteFailed")
      toast(msg, "error")
    }
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>

  return (
    <div className="space-y-6 animate-fade-in max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">{t("users.title")}</h1>
        <p className="text-muted-foreground text-sm mt-1">{t("users.subtitle")}</p>
      </div>

      {primaryAdmin && (
        <Card className="border-[#1877F2]/40 bg-[#1877F2]/5">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Crown className="h-5 w-5 text-[#1877F2]" />
              <CardTitle>{t("users.primaryTitle")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 p-4 rounded-lg border border-[#1877F2]/25 bg-card">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <p className="font-semibold text-base truncate">{primaryAdmin.full_name}</p>
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-[#1877F2] px-3.5 py-1 text-sm font-bold text-white shadow-md ring-2 ring-[#1877F2]/30">
                    <Crown className="h-4 w-4" />
                    {t("users.roleMainAdmin")}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground truncate">{primaryAdmin.email}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Plus className="h-5 w-5 text-primary" />
            <CardTitle>{t("users.addUser")}</CardTitle>
          </div>
          <CardDescription>{t("users.addUserDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>{t("users.fullName")}</Label>
            <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>{t("login.email")}</Label>
            <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label>{t("login.password")}</Label>
            <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          <div className="sm:col-span-2">
            <Button onClick={handleCreate} disabled={saving || !form.email || !form.password || !form.full_name}>
              {saving ? <Spinner /> : <><Plus className="h-4 w-4" /> {t("users.create")}</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <UserCog className="h-5 w-5 text-primary" />
            <CardTitle>{t("users.listTitle")}</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {teamUsers.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("users.emptyTeam")}</p>
          ) : (
            teamUsers.map((user) => (
              <div key={user.id} className="flex flex-col sm:flex-row sm:items-center gap-3 p-4 rounded-lg border">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <p className="font-medium truncate">{user.full_name}</p>
                    <Badge variant={user.is_active ? "default" : "secondary"}>{roleLabel(user, t)}</Badge>
                    {!user.is_active && <Badge variant="outline">{t("users.inactive")}</Badge>}
                  </div>
                  <p className="text-sm text-muted-foreground truncate">{user.email}</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button variant="outline" size="sm" onClick={() => toggleActive(user)}>
                    {user.is_active ? t("users.deactivate") : t("users.activate")}
                  </Button>
                  <Button variant="destructive" size="sm" onClick={() => handleDelete(user)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}
