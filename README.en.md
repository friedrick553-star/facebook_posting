# Facebook Marketplace Posting

Schedule: **Europe/Rome (Italy)** · Chromium: **Italian** (`it-IT`)

---

## Start

- **First time:** `setup.bat` (needs Python 3.11+, Node.js)
- **Every time:** `startall.bat` → http://localhost:5174
- **First visit:** set admin email + password → Save → Sign in
- Keep both CMD windows open (backend + frontend)

---

## Flow

- **Login** to dashboard
- **Users** — primary admin only; each user has separate cookies, products, and bot
- **Products** — upload CSV (`sample_products.csv`)
  - Required: `name`, `description`, `price`, `images`, `category`, `condition`, `availability`, `schedule_day`, `schedule_time`
  - Optional: `details`, `brand`, `color`
- **Settings**
  - Facebook cookies (optional)
  - **Test full flow** = hardcoded bicycle demo to Publish screen (**Publish NOT clicked**)
- **Start**
  - No products + no saved session → **Chromium opens immediately** (login)
  - Saved session + products → Chromium at **scheduled time** (Italy)
  - Test flow ON → hardcoded bicycle demo (not from CSV)
- **At scheduled time** (CSV products)
  - Chromium → full form → **Publish / Pubblica clicked** → **Published**
  - ~12s → Chromium closes → bot stays ON → next product
- **Stop** — bot OFF, Chromium closed

---

## Product status

- **Scheduled** · **Published** · **Failed** · **Missing fields** · **Duplicates**
