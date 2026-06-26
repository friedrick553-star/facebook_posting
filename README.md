Facebook Marketplace Posting

Orari: Europe/Rome (Italia) · Chromium: italiano (it-IT)

INSTALL (da Git)

- git clone <repo-url>
- cd facebook posting
- Copia backend\.env.example → backend\.env e compila ADMIN_EMAIL, ADMIN_PASSWORD, SMTP (opzionale)
- In backend\.env lascia: STOP_AFTER_MARKETPLACE=true e BROWSER_TIMEZONE=Europe/Rome
- Prima volta: doppio click su setup.bat (Python 3.11+ e Node.js)
- Ogni volta: doppio click su startall.bat → http://localhost:5174
- Tieni aperti i 2 CMD (backend + frontend)

AVVIO

- Prima visita: imposta email e password admin, Salva, poi Accedi
- Products: carica CSV (es. sample_products.csv)
  - Obbligatori: name, description, price, images, category, condition, availability, schedule_date, schedule_time
  - schedule_date: YYYY-MM-DD o DD/MM/YYYY · schedule_time: HH:MM (fuso Europe/Rome)
- Bot: dopo aver programmato i prodotti, premi Start in alto a destra e lascia ON
- Più prodotti alla stessa ora o ravvicinati → coda automatica (uno alla volta, senza blocchi)

FLUSSO

- Sessione Facebook salvata + prodotti programmati → bot in attesa; Chromium ~3,5 s prima dell’ora (Italia)
- All’ora programmata: form completo → Pubblica cliccata → Published → ~12 s → Chromium chiuso → prossimo in coda
- Stop: bot OFF, Chromium chiuso

STATI PRODOTTO

- Scheduled · Published · Failed · Missing fields · Duplicates

NOTE

- Orari = sempre Europe/Rome (Italia), non UTC né orologio PC
- Il bot pubblica in coda: finché uno non finisce, il successivo resta in attesa
- Categoria/condizione generiche nel CSV → il bot sceglie l’opzione Marketplace più simile
