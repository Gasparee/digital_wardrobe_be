import os
import io
import time
import base64
from typing import List
import bcrypt
import json

from fastapi import Depends, FastAPI, UploadFile, File, Form, HTTPException,Request
from starlette.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from rembg import remove, new_session
from PIL import Image
from services.routine_service import current_user, generate_code, get_cat_id, prepare_image_for_ai, setup_categories_obj

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from dotenv import load_dotenv
load_dotenv()

#AUTH PER NGROK
from pyngrok import ngrok
ngrok.set_auth_token(os.getenv("NGROK_AUTH_TOKEN"))
tunnel = ngrok.connect(8000)
os.environ["BASE_URL"] = tunnel.public_url
print(f"URL pubblico: {tunnel.public_url}")

# API AI PER ANALISI IMMAGINE
from groq import Groq
groq_client = Groq(api_key= os.getenv("GROQ_API_KEY"))

# --- SCHEMI DATI (PYDANTIC) ---
from models.model import UserRegister, UserLogin, OutfitSave, ItemDetail

# --- CONFIGURAZIONE CORE ---
app = FastAPI(title="Digital Wardrobe Pro - Server")

# CONFIGURAZIONE CARTELLE IMMAGINI
DEFAULT_FOLDER = os.getenv("DEFAULT_FOLDER", "img")
READY_FOLDER = os.getenv("READY_FOLDER", "ready")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "upload")
OUTFITS_FOLDER = os.getenv("OUTFITS_FOLDER", "outfits")
UPLOAD_DIR = os.path.join(DEFAULT_FOLDER, UPLOAD_FOLDER)
READY_DIR = os.path.join(DEFAULT_FOLDER, READY_FOLDER)
OUTFITS_DIR = os.path.join(DEFAULT_FOLDER, OUTFITS_FOLDER)

DEFAULT_MODEL_URL = "img/manichino.png"

for d in [UPLOAD_DIR, READY_DIR, OUTFITS_DIR]:
    os.makedirs(d, exist_ok=True)

# --- INIZIALIZZAZIONE MODELLO AI ---
my_session = new_session("isnet-general-use")
cloth_session = new_session("u2net_cloth_seg")

# --- MIDDLEWARE & STATICI ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class StaticFilesCORS(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

app.mount("/ready", StaticFilesCORS(directory=READY_DIR), name="ready")
app.mount("/unprocessed-files", StaticFilesCORS(directory=UPLOAD_DIR), name="unprocessed")
app.mount("/outfits-files", StaticFilesCORS(directory=OUTFITS_DIR), name="outfits")
app.mount("/static", StaticFilesCORS(directory="img"), name="static")
app.mount("/tryon-files", StaticFilesCORS(directory=os.path.join("img", "tryon")), name="tryon")


limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) 

# --- DATABASE ENGINE ---
from services.db_service import capi_mai_usati_in_outfit, create_category, create_item, create_item_detail, create_new_outfit_category, create_outfit, create_outfit_item, delete_item, delete_outfit, delete_outfit_category_by_id, get_bulk_items_by_user, get_category_by_user, get_colori_ammessi, get_db, get_filname_by_outfit_id, get_item_by_id, get_item_by_user_status, get_items_detail_by_id, get_items_for_ai_analysis_by_id, get_outfit_by_id_and_user, get_outfit_categories_by_user, get_outfit_category_by_id_and_user, get_outfit_category_genai, get_outfits_by_user, get_stats, get_stili_ammessi, get_tessuti_ammessi, get_user_by_email, init_db, items_preferiti, move_outfit_category, register_user, stiles_piu_usati, tessuti_piu_usati, tot_items, tot_outfit, update_item_category, update_item_status, update_user_token
init_db()


# --- API AUTENTICAZIONE ---
@app.post("/register")
async def register(user: UserRegister,conn = Depends(get_db)):
    if not user.password:
        raise HTTPException(status_code=400, detail="Password mancante")
    hashed_pwd = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt())
    user_id = register_user(conn, user.email, hashed_pwd, user.name)
    if not user_id:
        raise HTTPException(status_code=400, detail="Email già registrata")
    return {"message": "Registrazione completata"}

@app.post("/login")
@limiter.limit("5/minute")
async def login(request: Request,credentials: UserLogin,conn = Depends(get_db)):
    user = get_user_by_email(conn, credentials.email)
    if not user:
        raise HTTPException(status_code=401, detail="Email o password errati")
    stored_hash = user["password"]
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode("utf-8")
    if not bcrypt.checkpw(credentials.password.encode("utf-8"), stored_hash):
        raise HTTPException(status_code=401, detail="Email o password errati")
    new_token = update_user_token(conn, user["id"])
    return {"token": new_token, "name": user["name"], "email": user["email"]}

# --- API CATEGORIE ---
# GET: lista categorie dell'utente
@app.get("/categories")
async def get_categories_api(user: dict = Depends(current_user),conn = Depends(get_db)):
    categories = get_category_by_user(conn,user["id"])
    return {"categories": [{"id": r["id"], "name": r["name"]} for r in categories]}

# POST: crea nuova categoria
@app.post("/categories")
async def create_category_api(user: dict = Depends(current_user), name: str = Form(...), conn = Depends(get_db)):
    return create_category(conn,user['id'], name)

# PATCH: sposta capo in altra categoria
@app.patch("/items/{item_id}/category")
async def move_item_category_api(item_id: int, user: dict = Depends(current_user), new_category: str = Form(...), conn = Depends(get_db)):
    cat_id = get_cat_id(conn, user["id"], new_category)
    update_item_category(conn, item_id, user, cat_id)  # ← solo DB, niente file
    return {"status": "ok"}


# --- API GESTIONE CAPI (UPLOAD & INVENTORY) ---
# POST: upload immagini e creazione item in DB
@app.post("/upload")
async def upload_api(files: List[UploadFile] = File(...), category: str = Form(...), user: dict = Depends(current_user), conn = Depends(get_db)):
    if not category.strip():
        raise HTTPException(status_code=400, detail="Categoria mancante")
    cat_id = get_cat_id(conn, user["id"], category)
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
        safe_name = f"u{user['id']}_{generate_code()}{ext}"
        with open(os.path.join(UPLOAD_DIR, safe_name), "wb") as f:  # ← direttamente in UPLOAD_DIR
            f.write(await file.read())
        create_item(conn, user, cat_id, safe_name, UPLOAD_FOLDER)
    return {"status": "ok"}

# GET: dettagli di un capo (taglia, stile, tessuto, colore, descrizione, preferito)
@app.get("/items/details/bulk")
async def get_items_details_bulk_api(user: dict = Depends(current_user),conn = Depends(get_db)):
    rows = get_bulk_items_by_user(conn,user["id"])
    result = {}
    for row in rows:
        result[row["item_id"]] = {
            "item_id":    row["item_id"],
            "taglia":     row["taglia"]      or "",
            "stile":      row["stile"]       or "",
            "tessuto":    row["tessuto"]     or "",
            "colore":     row["colore"]      or "" if "colore"      in row.keys() else "",
            "descrizione":row["descrizione"] or "" if "descrizione" in row.keys() else "",
            "preferito":  bool(row["preferito"]) if "preferito" in row.keys() else False
        }
    return {"details": result}

# GET: dettaglio di un capo (taglia, stile, tessuto, colore, descrizione, preferito)
@app.get("/items/{item_id}/detail")
async def get_item_detail_api(item_id: int,user: dict = Depends(current_user),conn = Depends(get_db)):
    row = get_items_detail_by_id(conn,item_id)
    if not row:
        return {"item_id": item_id, "taglia": "", "stile": "", "tessuto": "", "colore": "", "descrizione": "", "preferito": False}
    return {
        "item_id":    row["item_id"],
        "taglia":     row["taglia"]     or "",
        "stile":      row["stile"]      or "",
        "tessuto":    row["tessuto"]    or "",
        "colore":     row["colore"]     or "" if "colore"     in row.keys() else "",
        "descrizione":row["descrizione"]or "" if "descrizione"in row.keys() else "",
        "preferito":  bool(row["preferito"]) if "preferito"  in row.keys() else False
    }


# GET: lista capi non ancora processati (status='upload')
@app.get("/unprocessed-inventory")
async def get_unprocessed_api(user: dict = Depends(current_user),conn = Depends(get_db)):
    return {"unprocessed": setup_categories_obj(get_item_by_user_status(conn,user["id"], UPLOAD_FOLDER),"unprocessed-files")}

# GET: lista capi processati (status='ready')
@app.get("/inventory")
async def get_inventory_api(user: dict = Depends(current_user),conn = Depends(get_db)):
    return {"inventory": setup_categories_obj(get_item_by_user_status(conn,user["id"], READY_FOLDER),READY_FOLDER)}

# --- API ELABORAZIONE AI ---
# POST: processo batch immagini non elaborate (rimozione sfondo + crop)
@app.post("/process-batch")
async def process_api(user: dict = Depends(current_user), conn = Depends(get_db)):
    items = get_item_by_user_status(conn, user["id"], UPLOAD_FOLDER)
    count = 0
    for i in items:
        in_p = os.path.join(UPLOAD_DIR, i["filename"])           # ← no subfolder cat
        print(f"Processando {in_p} per item_id {i['id']}")  # Debug percorso file
        out_n = os.path.splitext(i["filename"])[0] + ".png"
        out_p = os.path.join(READY_DIR, out_n)                   # ← direttamente in READY_DIR
        try:
            with open(in_p, 'rb') as f: data = f.read()
            clean = remove(data, session=my_session, post_process_mask=True)
            img = Image.open(io.BytesIO(clean))
            bbox = img.getbbox()
            if bbox: img = img.crop(bbox)
            img.save(out_p, "PNG")
            if os.path.exists(in_p): os.remove(in_p)
            update_item_status(conn, i["id"], out_n, READY_FOLDER)
            count += 1
        except Exception as e: print(f"Errore: {e}")
    return {"elaborati": count}

#DELETE: elimina un capo (sia file che record DB)
@app.delete("/items/{item_id}")
async def delete_item_api(item_id: int, user: dict = Depends(current_user), conn = Depends(get_db)):
    row = get_item_by_id(conn, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Capo non trovato")
    if row["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Non autorizzato")
    sub = UPLOAD_FOLDER if row["status"] == UPLOAD_FOLDER else READY_FOLDER
    p = os.path.join(sub, row["filename"])  # ← rimosso DEFAULT_FOLDER e cat
    if os.path.exists(p): os.remove(p)
    delete_item(conn, item_id)
    return {"status": "ok"}

# POST: salva dettagli di un capo (taglia, stile, tessuto, colore, descrizione, preferito)
@app.post("/items/{item_id}/detail")
async def save_item_detail_api(item_id: int, detail: ItemDetail, user: dict = Depends(current_user),conn = Depends(get_db)):    
    # Converti esplicitamente preferito in int
    preferito_int = 1 if detail.preferito else 0
    create_item_detail(conn, item_id, detail.taglia, detail.stile, detail.tessuto, detail.colore, detail.descrizione, preferito_int)
    return {"status": "ok"}

# --- API OUTFITS ---
# POST: salva outfit con immagine e lista item
@app.post("/save-outfit")
async def save_outfit_api(data: OutfitSave,user: dict = Depends(current_user),conn = Depends(get_db)):
    header, encoded = data.image.split(",", 1)
    file_bytes = base64.b64decode(encoded)
    fname = f"outfit_{user['id']}_{int(time.time())}.png"
    with open(os.path.join(OUTFITS_DIR, fname), "wb") as f: f.write(file_bytes)
    oid = create_outfit(conn, user["id"], fname, data.category_id)
    for iid in data.item_ids:
        create_outfit_item(conn, oid, iid)
    return {"status": "ok"}

# GET: lista outfit dell'utente con categorie
@app.get("/outfits")
async def get_outfits_api(user: dict = Depends(current_user),conn = Depends(get_db)):
    outfit = get_outfits_by_user(conn, user["id"])
    res = {}
    for r in outfit:
        cat = r["cat_name"] or "Senza categoria"
        if cat not in res: res[cat] = []
        res[cat].append({"id": r["id"], "path": f"/outfits-files/{r['filename']}"})
    return {"outfits": res}

# DELETE: elimina outfit (file + record DB)
@app.delete("/outfits/{oid}")
async def delete_outfit_api(oid: int, user: dict = Depends(current_user),conn = Depends(get_db)):
    row = get_filname_by_outfit_id(conn, oid)
    if not row:
        raise HTTPException(status_code=404, detail="Outfit non trovato")

    p = os.path.join(OUTFITS_DIR, row["filename"])
    if os.path.exists(p): os.remove(p)
    delete_outfit(conn, oid)
    return {"status": "ok"}


#--- API OUTFITS CATEGORIES ---
# GET: lista categorie outfit dell'utente
@app.get("/outfit-categories")
async def get_outfit_categories_api(user: dict = Depends(current_user),conn = Depends(get_db)):
    cats = [{"id": r["id"], "name": r["name"]} for r in get_outfit_categories_by_user(conn, user["id"])]
    return {"categories": cats}

# POST: crea nuova categoria outfit
@app.post("/outfit-categories")
async def create_outfit_category_api(name: str = Form(...), user: dict = Depends(current_user),conn = Depends(get_db)):
    return create_new_outfit_category(conn, user["id"], name)

# DELETE: elimina categoria outfit (solo record DB, outfit rimangono ma senza categoria)
@app.delete("/outfit-categories/{cat_id}")
async def delete_outfit_category_api(cat_id: int, user: dict = Depends(current_user),conn = Depends(get_db)):
    return delete_outfit_category_by_id(conn, cat_id, user["id"])

# PATCH: sposta outfit in altra categoria
@app.patch("/outfits/{outfit_id}/category")
async def move_outfit_category_api(outfit_id: int, user: dict = Depends(current_user), category_id: int = Form(...),conn = Depends(get_db)):
    if not get_outfit_category_by_id_and_user(conn, category_id, user["id"]):
        raise HTTPException(status_code=404, detail="Categoria non trovata")
    if not get_outfit_by_id_and_user(conn, outfit_id, user["id"]):
        raise HTTPException(status_code=404, detail="Outfit non trovato")
    move_outfit_category(conn, outfit_id, user["id"], category_id)
    return {"status": "ok"}

# --- API STATISTICHE ---
# GET: statistiche utente (capi per categoria, tessuti più usati, stili più usati, totale capi, preferiti, capi mai usati in outfit, totale outfit)
@app.get("/stats")
async def get_stats_api(user: dict = Depends(current_user),conn = Depends(get_db)):
    per_categoria = [{"name": r["name"], "count": r["count"]} for r in get_stats(conn, user['id'])]
    # Tessuto più usato
    tessuto_counter = {}
    for row in tessuti_piu_usati(conn, user["id"]):
        for t in row["tessuto"].split(","):
            t = t.strip()
            if t: tessuto_counter[t] = tessuto_counter.get(t, 0) + 1
    tessuti_sorted = sorted(tessuto_counter.items(), key=lambda x: x[1], reverse=True)
    # Stile più usato
    stile_counter = {}
    for row in stiles_piu_usati(conn, user["id"]):
        for s in row["stile"].split(","):
            s = s.strip()
            if s: stile_counter[s] = stile_counter.get(s, 0) + 1
    stili_sorted = sorted(stile_counter.items(), key=lambda x: x[1], reverse=True)
    # Totale capi
    total_items = tot_items(conn, user["id"], READY_FOLDER)
    # Preferiti
    total_preferiti = items_preferiti(conn, user["id"])
    # Capi mai usati in outfit
    mai_usati = capi_mai_usati_in_outfit(conn, user["id"],READY_FOLDER)
    # Totale outfit
    total_outfits = tot_outfit(conn, user_id=user["id"])
    
    return {
        "per_categoria": per_categoria,
        "tessuti": tessuti_sorted,
        "stili": stili_sorted,
        "total_items": total_items,
        "total_preferiti": total_preferiti,
        "mai_usati": mai_usati,
        "total_outfits": total_outfits
    }


# ---- API ANALISI IMMAGINE AI (GROQ Vision + LLM)
# POST: analizza un capo tramite AI e restituisce descrizione, colori, stili, tessuti
@app.post("/items/{item_id}/analyze-ai")
async def analyze_item_ai_api(item_id: int,user: dict = Depends(current_user),conn = Depends(get_db)):
    row = get_items_for_ai_analysis_by_id(conn, user["id"], item_id, READY_FOLDER)
    if not row:
        raise HTTPException(status_code=404, detail="Capo non trovato")

    image_path = os.path.join(READY_DIR, row["filename"])
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="File immagine non trovato")

    # Converti immagine in base64
    #with open(image_path, "rb") as f:
     #   image_b64 = base64.b64encode(f.read()).decode("utf-8")
    image_b64 = prepare_image_for_ai(image_path, max_size=256)

    prompt = """Analizza il capo d'abbigliamento. Rispondi SOLO con JSON:
    {"descrizione":"2-3 frasi in italiano","colori":[],"stili":[],"tessuti":[]}

    Colori ammessi: Bianco,Nero,Grigio,Rosso,Rosa,Arancio,Giallo,Verde,Turchese,Blu,Blu Navy,Viola,Marrone,Beige
    Stili ammessi: Sera,Giorno,Casual,Elegante,Sportivo
    Tessuti ammessi: Lana,Cotone,Lino,Jeans,Seta"""

    try:
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                #"url": f"data:image/png;base64,{image_b64}"
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            max_tokens=200,
            temperature=0.3
        )

        raw = response.choices[0].message.content.strip()

        # Pulizia risposta nel caso ci siano backtick
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        # Valida e filtra i valori ammessi
        STILI_AMMESSI   = get_stili_ammessi(conn)
        TESSUTI_AMMESSI = get_tessuti_ammessi(conn)
        COLORI_AMMESSI  = get_colori_ammessi(conn)

        return {
            "descrizione": result.get("descrizione", ""),
            "colori":  [c for c in result.get("colori",  []) if c in COLORI_AMMESSI],
            "stili":   [s for s in result.get("stili",   []) if s in STILI_AMMESSI],
            "tessuti": [t for t in result.get("tessuti", []) if t in TESSUTI_AMMESSI],
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Errore nel parsing della risposta AI")
    except Exception as e:
        print(f"Errore Groq Vision: {e}")
        raise HTTPException(status_code=500, detail=f"Errore AI: {str(e)}")
    
    
# --- AVVIO SERVER ---
if __name__ == "__main__":
    import uvicorn
    #uvicorn main:app --reload
    uvicorn.run(app, host="0.0.0.0", port=8000)