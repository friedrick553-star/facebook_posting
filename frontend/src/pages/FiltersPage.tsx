import { useEffect, useState, type ReactNode } from "react"
import { Save, X, Check } from "lucide-react"
import { getFilters, createFilter, updateFilter } from "@/lib/api"
import type { Filter } from "@/types"
import { Button } from "@/components/ui/button"
import { Input, Label } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Spinner, Badge } from "@/components/ui/badge"
import { useToast } from "@/contexts/ToastContext"

const defaultFilter = (): Partial<Filter> => ({
  name: "Vehicle Search",
  is_active: true,
  country: "Switzerland",
  city: "Zurich",
  radius_km: 65,
  brands: [],
  models: [],
  fuel_types: [],
  transmission_types: [],
  price_min: null,
  price_max: null,
  mileage_min: null,
  mileage_max: null,
  year_min: null,
  year_max: null,
  min_match_score: 80,
  include_keywords: [],
  exclude_keywords: [],
})

function RequiredLabel({ children }: { children: ReactNode }) {
  return (
    <Label>
      {children}
      <span className="text-destructive ml-0.5" aria-hidden="true">*</span>
    </Label>
  )
}

function TagInput({
  label,
  values,
  onChange,
  placeholder,
  required = false,
}: {
  label: string
  values: string[]
  onChange: (v: string[]) => void
  placeholder?: string
  required?: boolean
}) {
  const [input, setInput] = useState("")
  const add = () => {
    const trimmed = input.trim()
    if (trimmed && !values.includes(trimmed)) {
      onChange([...values, trimmed])
      setInput("")
    }
  }
  return (
    <div className="space-y-2">
      {required ? <RequiredLabel>{label}</RequiredLabel> : <Label>{label}</Label>}
      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder={placeholder || "Type and press Enter or Add..."}
        />
        <Button type="button" variant="outline" size="sm" onClick={add}>Add</Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {values.map((v) => (
          <Badge key={v} variant="secondary" className="gap-1 cursor-pointer" onClick={() => onChange(values.filter((x) => x !== v))}>
            {v} <X className="h-3 w-3" />
          </Badge>
        ))}
      </div>
    </div>
  )
}

function validateFilterForm(form: Partial<Filter>): string | null {
  if (!form.city?.trim()) return "City is required (Facebook Marketplace search)"
  if (!form.country?.trim()) return "Country / Region is required (Facebook Marketplace search)"
  if (!form.radius_km || form.radius_km <= 0) return "Radius (km) is required (Facebook Marketplace search)"
  if (form.price_min == null || form.price_min <= 0) return "Min Price (CHF) is required (Facebook Marketplace search)"
  if (form.price_max == null || form.price_max <= 0) return "Max Price (CHF) is required (Facebook Marketplace search)"
  if (form.price_max < form.price_min) return "Max Price must be greater than or equal to Min Price"
  if (!form.brands?.length) return "At least one Vehicle Brand is required (Match & Email)"
  if (!form.models?.length) return "At least one Vehicle Model is required (Match & Email)"
  if (form.min_match_score == null || form.min_match_score < 0 || form.min_match_score > 100) {
    return "Min Match Score (0–100) is required (Match & Email)"
  }
  return null
}

export default function FiltersPage() {
  const [form, setForm] = useState<Partial<Filter>>(defaultFilter())
  const [filterId, setFilterId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const { toast } = useToast()

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await getFilters()
      if (data.length > 0) {
        setForm({ ...data[0] })
        setFilterId(data[0].id)
      } else {
        setForm(defaultFilter())
        setFilterId(null)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const updateForm = (updates: Partial<Filter>) => {
    setForm((prev) => ({ ...prev, ...updates }))
    setSaved(false)
  }

  const handleSave = async () => {
    const validationError = validateFilterForm(form)
    if (validationError) {
      toast(validationError, "warning")
      return
    }

    const payload = {
      ...form,
      name: form.name?.trim() || "Vehicle Search",
      is_active: true,
      search_url: null,
    }
    setSaving(true)
    try {
      if (filterId) {
        await updateFilter(filterId, payload)
      } else {
        const { data } = await createFilter(payload)
        setFilterId(data.id)
        setForm({ ...data })
      }
      setSaved(true)
    } catch {
      toast("Failed to save filters", "error")
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner className="h-8 w-8" /></div>

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Filters</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Step 1 searches Facebook Marketplace. Step 2 picks accurate matches and sends email alerts. Fields marked with{" "}
          <span className="text-destructive">*</span> are required to save.
        </p>
      </div>

      <div className="space-y-2 max-w-md">
        <Label>Filter Name</Label>
        <Input value={form.name || ""} onChange={(e) => updateForm({ name: e.target.value })} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>1. Facebook Marketplace Search</CardTitle>
          <CardDescription>
            Like Facebook: set location (city + radius) → open Vehicles → apply sidebar filters. These fetch the initial results.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div>
            <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-3">Location</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2"><RequiredLabel>City</RequiredLabel><Input value={form.city || ""} onChange={(e) => updateForm({ city: e.target.value })} placeholder="e.g. Zurich" /></div>
              <div className="space-y-2"><RequiredLabel>Country / Region</RequiredLabel><Input value={form.country || ""} onChange={(e) => updateForm({ country: e.target.value })} placeholder="e.g. Switzerland" /></div>
              <div className="space-y-2"><RequiredLabel>Radius (km)</RequiredLabel><Input type="number" min={1} value={form.radius_km ?? ""} onChange={(e) => updateForm({ radius_km: Number(e.target.value) })} /></div>
            </div>
          </div>

          <div>
            <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-3">Vehicles — Price</h3>
            <div className="grid grid-cols-2 gap-4 max-w-md">
              <div className="space-y-2"><RequiredLabel>Min Price (CHF)</RequiredLabel><Input type="number" min={1} value={form.price_min ?? ""} onChange={(e) => updateForm({ price_min: Number(e.target.value) || null })} /></div>
              <div className="space-y-2"><RequiredLabel>Max Price (CHF)</RequiredLabel><Input type="number" min={1} value={form.price_max ?? ""} onChange={(e) => updateForm({ price_max: Number(e.target.value) || null })} /></div>
            </div>
          </div>

        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Match & Email Alerts</CardTitle>
          <CardDescription>
            After Facebook returns listings, these refine accurate matches. Email is sent only when match score meets your minimum.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <TagInput required label="Vehicle Brands (Make)" values={form.brands || []} onChange={(v) => updateForm({ brands: v })} placeholder="e.g. Volkswagen, Audi" />
          <TagInput required label="Vehicle Models" values={form.models || []} onChange={(v) => updateForm({ models: v })} placeholder="e.g. VW Golf" />
          <TagInput label="Fuel Types" values={form.fuel_types || []} onChange={(v) => updateForm({ fuel_types: v })} placeholder="e.g. Petrol, 2.0 TDI" />
          <TagInput label="Transmission Types" values={form.transmission_types || []} onChange={(v) => updateForm({ transmission_types: v })} placeholder="e.g. DSG, Automatic" />

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="space-y-2"><Label>Mileage Min</Label><Input type="number" value={form.mileage_min ?? ""} onChange={(e) => updateForm({ mileage_min: Number(e.target.value) || null })} /></div>
            <div className="space-y-2"><Label>Mileage Max</Label><Input type="number" value={form.mileage_max ?? ""} onChange={(e) => updateForm({ mileage_max: Number(e.target.value) || null })} /></div>
            <div className="space-y-2"><Label>Year Min</Label><Input type="number" value={form.year_min ?? ""} onChange={(e) => updateForm({ year_min: Number(e.target.value) || null })} /></div>
            <div className="space-y-2"><Label>Year Max</Label><Input type="number" value={form.year_max ?? ""} onChange={(e) => updateForm({ year_max: Number(e.target.value) || null })} /></div>
          </div>

          <div className="space-y-2 max-w-xs">
            <RequiredLabel>Min Match Score (%)</RequiredLabel>
            <Input type="number" min={0} max={100} value={form.min_match_score ?? 80} onChange={(e) => updateForm({ min_match_score: Number(e.target.value) })} />
          </div>

          <TagInput
            label="Include Keywords"
            values={form.include_keywords || []}
            onChange={(v) => updateForm({ include_keywords: v })}
            placeholder="e.g. DSG, Serviceheft gepflegt"
          />
          <TagInput
            label="Exclude Keywords"
            values={form.exclude_keywords || []}
            onChange={(v) => updateForm({ exclude_keywords: v })}
            placeholder="e.g. Motorschaden, Defekt"
          />
        </CardContent>
      </Card>

      <Button onClick={handleSave} disabled={saving}>
        {saving ? (
          <Spinner />
        ) : saved ? (
          <><Check className="h-4 w-4" /> Saved</>
        ) : (
          <><Save className="h-4 w-4" /> Save</>
        )}
      </Button>
    </div>
  )
}
