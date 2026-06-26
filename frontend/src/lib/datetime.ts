import type { Language } from "@/lib/i18n/translations"
import { POSTING_TIMEZONE } from "@/lib/schedule"

/** Backend stores UTC; SQLite may omit the Z suffix — always treat as UTC. */
export function parseApiDate(iso: string): Date {
  const raw = iso.trim()
  if (!raw) return new Date(NaN)
  if (/[Zz]$/.test(raw) || /[+-]\d{2}:\d{2}$/.test(raw)) {
    return new Date(raw)
  }
  return new Date(`${raw}Z`)
}

export function formatAppDateTime(
  date: string | Date,
  language: Language = "it",
  opts?: { withSeconds?: boolean },
): string {
  const d = typeof date === "string" ? parseApiDate(date) : date
  if (Number.isNaN(d.getTime())) return "—"
  const locale = language === "it" ? "it-IT" : "en-GB"
  return d.toLocaleString(locale, {
    timeZone: POSTING_TIMEZONE,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: opts?.withSeconds ? "2-digit" : undefined,
    hour12: false,
  })
}
