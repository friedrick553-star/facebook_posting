# Facebook Marketplace Posting

<i>

_Orari: **Europe/Rome (Italia)** · Chromium: **italiano** (`it-IT`)_

---

## Avvio

- **Prima volta:** `setup.bat` (Python 3.11+, Node.js richiesti)
- **Ogni volta:** `startall.bat` → http://localhost:5174
- **Prima visita:** imposta email + password admin → Salva → Accedi
- Tieni aperti i 2 CMD (backend + frontend)

---

## Flusso

- **Login** dashboard
- **Users** — solo admin principale; ogni utente ha cookie, prodotti e bot separati
- **Products** — carica CSV (`sample_products.csv`)
  - Obbligatori: `name`, `description`, `price`, `images`, `category`, `condition`, `availability`, `schedule_day`, `schedule_time`
  - Opzionali: `details`, `brand`, `color`
- **Settings**
  - Cookie Facebook (opzionale)
  - **Test flusso completo** = demo bicicletta fino a Pubblica (**Pubblica NON cliccata**)
- **Start**
  - Nessun prodotto + nessuna sessione → **Chromium subito** (login)
  - Sessione salvata + prodotti → Chromium all’**ora programmata** (Italia)
  - Test flow ON → demo bicicletta hardcoded (non da CSV)
- **All’ora programmata** (prodotti CSV)
  - Chromium → form completo → **Pubblica cliccata** → stato **Published**
  - ~12s → Chromium chiuso → bot ON → prossimo prodotto
- **Stop** — bot OFF, Chromium chiuso

---

## Stati prodotti

- **Scheduled** · **Published** · **Failed** · **Missing fields** · **Duplicates**

---

[README.en.md](README.en.md)

</i>
