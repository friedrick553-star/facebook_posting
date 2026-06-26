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
  - Obbligatori: name, description, price, images, category, condition, availability, schedule_date, schedule_time
  - schedule_date: YYYY-MM-DD o DD/MM/YYYY · schedule_time: HH:MM (fuso Europe/Rome)
  - Opzionali: details, brand, color
- Settings: cookie Facebook opzionali; Test flusso completo = demo bicicletta fino a schermata Pubblica (Pubblica NON cliccata, solo prova)
- Start:
  - Nessun prodotto programmato e nessuna sessione Facebook → Chromium si apre subito per login
  - Sessione salvata e prodotti programmati → bot in attesa; Chromium ~3,5 s prima dell’ora (Italia)
  - Test flow attivo → demo bicicletta hardcoded, non da CSV
- All’ora programmata (prodotti CSV):
  - Chromium apre ~3,5 s prima dell’orario
  - Form completo → Pubblica cliccata → prodotto Published
  - Circa 12 secondi → Chromium si chiude → bot resta ON per il prossimo prodotto
- Stop: bot OFF, Chromium chiuso

STATI PRODOTTO

- Scheduled — in attesa dell’orario programmato
- Published — pubblicato su Marketplace
- Failed — errore o orario perso (dopo 5 min di tolleranza)
- Missing fields — campi obbligatori mancanti nel CSV
- Duplicates — stesso contenuto già presente

NOTE

- Tutti gli orari schedule_date + schedule_time sono Europe/Rome, non UTC né l'orologio del PC
- Il bot sceglie sempre il prossimo slot futuro più vicino
- Categoria e condizione: valori generici nel CSV (es. solo "used") → il bot sceglie l'opzione Marketplace più simile
- Dopo Stop + Start, la pubblicazione programmata riprende normalmente
