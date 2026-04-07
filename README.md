# 👗 Digital Wardrobe Pro

Un backend RESTful per la gestione del proprio guardaroba digitale. Permette di catalogare capi d'abbigliamento, rimuoverne lo sfondo con l'AI, analizzarli tramite visione artificiale e comporre outfit salvabili.

---

## ✨ Funzionalità principali

- **Registrazione e login** con password hashata (bcrypt) e autenticazione token
- **Upload capi** con categorizzazione e rimozione sfondo automatica (rembg)
- **Analisi AI** dei capi tramite Groq Vision (Llama 4) — rileva colori, stili, tessuti e genera una descrizione
- **Gestione outfit** — crea, salva e organizza look in categorie personalizzate
- **Statistiche guardaroba** — capi per categoria, tessuti e stili più usati, preferiti, capi mai abbinati
- **Rate limiting** e tunnel pubblico via ngrok

---

## 🗂 Struttura del progetto

```
├── main.py                  # Entry point FastAPI, tutte le route API
├── models/
│   └── model.py             # Schemi Pydantic (UserRegister, OutfitSave, ecc.)
├── services/
│   ├── db_service.py        # Tutte le query SQLite e init del DB
│   └── routine_service.py   # Utility (auth, immagini, categorie)
├── img/
│   ├── upload/              # Immagini caricate in attesa di elaborazione
│   ├── ready/               # Immagini elaborate (sfondo rimosso)
│   ├── outfits/             # Immagini degli outfit salvati
│   └── tryon/               # (riservato a funzionalità try-on)
└── wardrobe_v3.db           # Database SQLite (generato automaticamente)
```

---

## 🚀 Installazione

### Prerequisiti

- Python 3.10+
- pip

### Setup

```bash
# 1. Clona il repository
git clone https://github.com/tuo-utente/digital-wardrobe-pro.git
cd digital-wardrobe-pro

# 2. Crea e attiva un ambiente virtuale
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Installa le dipendenze
pip install -r requirements.txt
```

### Variabili d'ambiente

Crea un file `.env` nella root del progetto:

```env
GROQ_API_KEY=la_tua_chiave_groq
NGROK_AUTH_TOKEN=il_tuo_token_ngrok
DB_NAME=wardrobe_v3.db

# Cartelle immagini (opzionale, ha già i default)
DEFAULT_FOLDER=img
UPLOAD_FOLDER=upload
READY_FOLDER=ready
OUTFITS_FOLDER=outfits
```

### Avvio

```bash
uvicorn main:app --reload
```

Il server partirà su `http://localhost:8000`. All'avvio verrà stampato anche l'URL pubblico ngrok.

---

## 📦 Dipendenze principali

| Libreria | Scopo |
|---|---|
| `fastapi` | Framework web |
| `uvicorn` | Server ASGI |
| `rembg` | Rimozione sfondo AI |
| `Pillow` | Elaborazione immagini |
| `groq` | Client Groq Vision (LLM) |
| `bcrypt` | Hashing password |
| `slowapi` | Rate limiting |
| `pyngrok` | Tunnel pubblico |
| `python-dotenv` | Gestione variabili d'ambiente |

---

## 🔌 API Reference

### Autenticazione

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `POST` | `/register` | Registrazione nuovo utente |
| `POST` | `/login` | Login (max 5 richieste/minuto) |

### Categorie

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `GET` | `/categories` | Lista categorie dell'utente |
| `POST` | `/categories` | Crea nuova categoria |
| `PATCH` | `/items/{item_id}/category` | Sposta un capo in un'altra categoria |

### Capi (Items)

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `POST` | `/upload` | Carica uno o più capi |
| `GET` | `/inventory` | Lista capi elaborati |
| `GET` | `/unprocessed-inventory` | Lista capi non ancora elaborati |
| `POST` | `/process-batch` | Elabora batch (rimozione sfondo + crop) |
| `GET` | `/items/{item_id}/detail` | Dettaglio di un capo |
| `POST` | `/items/{item_id}/detail` | Salva dettagli (taglia, stile, tessuto…) |
| `GET` | `/items/details/bulk` | Dettagli di tutti i capi in una sola chiamata |
| `DELETE` | `/items/{item_id}` | Elimina un capo |
| `POST` | `/items/{item_id}/analyze-ai` | Analisi AI del capo (Groq Vision) |

### Outfit

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `GET` | `/outfits` | Lista outfit dell'utente |
| `POST` | `/save-outfit` | Salva un outfit (immagine + lista item) |
| `DELETE` | `/outfits/{oid}` | Elimina un outfit |
| `PATCH` | `/outfits/{outfit_id}/category` | Sposta outfit in un'altra categoria |

### Categorie Outfit

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `GET` | `/outfit-categories` | Lista categorie outfit |
| `POST` | `/outfit-categories` | Crea categoria outfit |
| `DELETE` | `/outfit-categories/{cat_id}` | Elimina categoria outfit |

### Statistiche

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `GET` | `/stats` | Statistiche complete del guardaroba |

---

## 🗄 Schema del Database

Il database SQLite viene inizializzato automaticamente al primo avvio.

```
users              → utenti registrati
categories         → categorie capi (per utente)
items              → capi d'abbigliamento
items_detail       → dettagli capo (taglia, stile, tessuto, colore, preferito)
outfits            → outfit salvati
outfit_items       → ponte outfit ↔ capi
outfit_categories  → categorie outfit (per utente)
stili_ammessi      → valori ammessi per lo stile
tessuti_ammessi    → valori ammessi per il tessuto
colori_ammessi     → valori ammessi per il colore
```

---

## 🤖 Analisi AI

L'endpoint `/items/{item_id}/analyze-ai` invia l'immagine del capo (ridimensionata a 256px e convertita in JPEG per ottimizzare i token) al modello **Llama 4 Scout** via Groq Vision.

La risposta viene validata rispetto ai valori ammessi nel database e restituisce:

```json
{
  "descrizione": "Una giacca in lana grigia dal taglio classico...",
  "colori": ["Grigio"],
  "stili": ["Elegante", "Giorno"],
  "tessuti": ["Lana"]
}
```

---

## 🔒 Sicurezza

- Le password sono hashate con **bcrypt**
- I token di sessione vengono hashati con **SHA-256** prima di essere salvati nel DB
- Il login è protetto da **rate limiting** (5 richieste/minuto per IP)
- Ogni operazione sugli item verifica che l'utente sia il proprietario

---

## 📝 Note

- Il file `.env` non va mai committato (aggiungilo a `.gitignore`)
- Il database `wardrobe_v3.db` e la cartella `img/` sono locali e vanno esclusi dal repository
- La documentazione interattiva delle API è disponibile su `http://localhost:8000/docs` (Swagger UI)
