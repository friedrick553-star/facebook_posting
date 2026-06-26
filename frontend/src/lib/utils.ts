import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

import type { Language } from "@/lib/i18n/translations"
import { formatAppDateTime } from "@/lib/datetime"

export function formatDate(date: string | Date, language: Language = "it") {
  return formatAppDateTime(date, language)
}

export function formatPrice(price: number | null | undefined, currency = "CHF") {
  if (price == null) return "N/A"
  return `${currency} ${price.toLocaleString("de-CH")}`
}

export function formatMileage(mileage: number | null | undefined) {
  if (mileage == null) return "N/A"
  return `${mileage.toLocaleString("de-CH")} km`
}

export const SCAN_DELAY_PRESETS = [
  { label: "30–45 s", min: 30, max: 45 },
  { label: "30–60 s", min: 30, max: 60 },
  { label: "45–90 s", min: 45, max: 90 },
  { label: "60–120 s", min: 60, max: 120 },
  { label: "90–180 s", min: 90, max: 180 },
]

export function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds} sec`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (s === 0) return `${m} min`
  return `${m} min ${s} sec`
}

/** User-facing check interval, e.g. "30–45 sec (random)" */
export function formatIntervalRange(minSec: number, maxSec: number, language: Language = "it") {
  const random = language === "it" ? "casuale" : "random"
  if (minSec === maxSec) return `${minSec} sec`
  return `${minSec}–${maxSec} sec (${random})`
}
