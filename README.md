Facebook Marketplace Posting

Orari: Europe/Rome (Italia) · Chromium: italiano (it-IT)

AVVIO

- Prima volta: doppio click su setup.bat (serve Python 3.11+ e Node.js)
- Ogni volta: doppio click su startall.bat
- Si apre http://localhost:5174
- Prima visita: imposta email e password admin, Salva, poi Accedi
- Tieni aperti i 2 CMD (backend e frontend)

FLUSSO

- Login alla dashboard
- Users: solo admin principale; ogni utente ha cookie, prodotti e bot separati
- Products: carica CSV (es. sample_products.csv)
  - Obbligatori: name, description, price, images, category, condition, availability, schedule_day, schedule_time
  - Opzionali: details, brand, color
- Settings: cookie Facebook opzionali; Test flusso completo = demo bicicletta fino a Pubblica (Pubblica NON cliccata)
- Start:
  - Nessun prodotto e nessuna sessione Facebook → Chromium si apre subito per login
  - Sessione salvata e prodotti in CSV → Chromium all ora programmata (Italia)
  - Test flow attivo → demo bicicletta hardcoded, non da CSV
- All ora programmata (prodotti CSV):
  - Chromium apre → form completo → Pubblica cliccata → prodotto Published
  - Circa 12 secondi → Chromium si chiude → bot resta ON per il prossimo prodotto
- Stop: bot OFF, Chromium chiuso

STATI PRODOTTO

- Scheduled
- Published
- Failed
- Missing fields
- Duplicates

English: README.en.md
