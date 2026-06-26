/** All product schedules use Europe/Rome (Italy) — same as Chromium/Facebook bot. NOT UTC, NOT PC local. */
export const POSTING_TIMEZONE = "Europe/Rome"

/** ISO date (YYYY-MM-DD) in Italy for HTML date inputs. */
export function todayIsoDate(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: POSTING_TIMEZONE }).format(new Date())
}

export function formatItalyNow(): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: POSTING_TIMEZONE,
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date())
}

export function italyUtcOffsetLabel(): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: POSTING_TIMEZONE,
      timeZoneName: "shortOffset",
    }).formatToParts(new Date())
    return parts.find((p) => p.type === "timeZoneName")?.value ?? POSTING_TIMEZONE
  } catch {
    return POSTING_TIMEZONE
  }
}

/** PC local time — for comparison only; scheduling always uses Italy. */
export function formatPcNow(): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date())
}

export function formatScheduleDisplay(date: string | null, time: string | null): string {
  if (!date && !time) return "—"
  let dateLabel = date || "—"
  if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
    dateLabel = new Intl.DateTimeFormat(undefined, {
      timeZone: POSTING_TIMEZONE,
      dateStyle: "medium",
    }).format(new Date(`${date}T12:00:00Z`))
  }
  const suffix = time ? ` · ${time}` : ""
  return `${dateLabel}${suffix} (Italia)`
}

export function normalizeScheduleDate(value: string | null | undefined): string {
  if (value && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  return todayIsoDate()
}

/** Build schedule_time (HH:MM) for N minutes from now in Italy. */
export function italyTimeInMinutes(minutesFromNow: number): { date: string; time: string } {
  const target = new Date(Date.now() + minutesFromNow * 60_000)
  const date = new Intl.DateTimeFormat("en-CA", { timeZone: POSTING_TIMEZONE }).format(target)
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: POSTING_TIMEZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(target)
  const hour = parts.find((p) => p.type === "hour")?.value ?? "00"
  const minute = parts.find((p) => p.type === "minute")?.value ?? "00"
  return { date, time: `${hour}:${minute}` }
}
