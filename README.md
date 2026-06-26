# Facebook Marketplace Posting

**Orari:** Europe/Rome (Italia) · **Chromium:** italiano (it-IT)

---

## Installazione (Git — installazione pulita)

Ogni **nuovo clone** parte da zero:

- Database SQLite **vuoto** (nessun prodotto, nessuna sessione Facebook)
- Cartella `backend/data/` creata al primo `setup.bat`
- Admin, SMTP e login Facebook li configuri tu sul PC del client

### Passi

1. `git clone https://github.com/friedrick553-star/facebook_posting.git`
2. `cd facebook_posting`
3. `copy backend\.env.example backend\.env`
4. In `backend\.env` compila:
   - `ADMIN_EMAIL` e `ADMIN_PASSWORD` (login dashboard)
   - SMTP (opzionale — email promemoria login Facebook)
   - Lascia: `STOP_AFTER_MARKETPLACE=true`, `BROWSER_TIMEZONE=Europe/Rome`, `PLAYWRIGHT_HEADLESS=false`
5. **Prima volta:** doppio click su `setup.bat` (serve Python 3.11+ e Node.js)
6. **Ogni avvio:** doppio click su `startall.bat` → http://localhost:5174
7. Tieni aperti i 2 CMD (backend + frontend)

---

## Primo avvio dashboard

1. Apri http://localhost:5174
2. Prima visita: imposta email e password admin → **Salva** → **Accedi**
3. **Products** → carica il CSV (`sample_products.csv` come esempio)
4. Controlla la lista **Scheduled** — date e ore in fuso **Italia**
5. Premi **Start** in alto a destra e **lascia ON** fino a fine pubblicazioni

---

## File CSV — formato e regole

### Colonne obbligatorie

| Colonna | Esempio | Note |
|---------|---------|------|
| `name` | iPhone 13 Pro 128GB | Titolo annuncio |
| `description` | Smartphone Apple... | Testo completo |
| `price` | 620 | Solo numero |
| `images` | url1\|url2 | Più URL separati da `\|` |
| `category` | Cell Phones | Categoria Marketplace |
| `condition` | new / used | Accetta anche italiano (nuovo, usato) |
| `availability` | single | Articolo singolo |
| `schedule_date` | 2026-06-28 oppure 28/06/2026 | Data **Italia** |
| `schedule_time` | 11:15 | Ora **HH:MM** fuso **Europe/Rome** |

### Colonne opzionali

- `details` — es. `Brand=Apple|Model=iPhone 13 Pro|Color=Blu`
- `currency` — default EUR

### Intervallo tra prodotti (importante)

Lascia **almeno 10–15 minuti** tra un prodotto e l’altro. Meglio **20–25 minuti** se hai molti annunci.

| Gap consigliato | Perché |
|-----------------|--------|
| **10–15 min** | Minimo — ogni post richiede ~5–8 min (form + Pubblica + chiusura browser) |
| **20–25 min** | Ideale — margine sicuro, meno rischio coda lunga o sessione Facebook |

- Stessa ora per più prodotti → **coda automatica** (uno alla volta, tag **In coda** / **Queued**)
- Il bot non apre due Chromium insieme

### Esempio CSV (3 prodotti con gap 20 min)

```csv
name,description,price,images,category,condition,availability,details,schedule_date,schedule_time
iPhone 13 Pro,Smartphone Apple 128GB,620,https://example.com/img1.jpg,Cell Phones,new,single,Brand=Apple,2026-06-28,10:00
Divano grigio,Divano 3 posti come nuovo,450,https://example.com/img2.jpg,Furniture,new,single,Brand=IKEA,2026-06-28,10:20
Bici elettrica,E-bike pieghevole,890,https://example.com/img3.jpg,Bicycles,new,single,,2026-06-28,10:45
```

Usa `sample_products.csv` nella root del progetto come modello completo.

---

## Flusso bot (Start ON)

| Situazione | Cosa succede |
|------------|--------------|
| **Nessun cookie Facebook + nessun prodotto programmato** | Chromium si apre **subito** al Start (login Marketplace), poi si chiude |
| **Prodotti programmati** | Bot in attesa — Chromium si apre **~3,5 s prima** dell’ora (Italia) |
| **All’ora programmata** | Form compilato → **Pubblica** cliccata → stato **Published** → ~12 s → Chromium chiuso → prossimo in coda |
| **Stop** | Bot OFF, Chromium chiuso |

---

## Stati prodotto

| Stato | Significato |
|-------|-------------|
| Scheduled / Programmato | In attesa dell’ora |
| In coda / Queued | Un altro post è in pubblicazione — questo aspetta |
| Publishing / In pubblicazione | Pubblicazione in corso |
| Published / Pubblicato | Completato su Marketplace |
| Failed / Fallito | Errore — controlla log, riprova |
| Missing fields | CSV incompleto |

---

## Note

- Orari = **sempre Europe/Rome (Italia)**, non UTC né orologio del PC
- Categoria/condizione generiche nel CSV → il bot sceglie l’opzione Marketplace più simile
- Sessione Facebook salvata in `backend/data/users/<id>/facebook_session.json` (non in Git)
- Database locale: `backend/data/facebook_posting.db`
