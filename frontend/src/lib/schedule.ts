/** ISO date (YYYY-MM-DD) for HTML date inputs — local calendar day. */
export function todayIsoDate(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

export function formatScheduleDisplay(date: string | null, time: string | null): string {
  if (!date && !time) return "—"
  let dateLabel = date || "—"
  if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
    const [y, mo, d] = date.split("-").map(Number)
    dateLabel = new Date(y, mo - 1, d).toLocaleDateString()
  }
  return time ? `${dateLabel} · ${time}` : dateLabel
}

export function normalizeScheduleDate(value: string | null | undefined): string {
  if (value && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  return todayIsoDate()
}
