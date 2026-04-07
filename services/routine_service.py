
import io
import base64
import string
import random

from PIL import Image
from fastapi import Depends, HTTPException

from services.db_service import categories_id_by_name, create_category, get_db, get_user_by_token
from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def generate_code(length=20):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def current_user(token: str = Depends(oauth2_scheme),conn = Depends(get_db)) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Token mancante")
    user = get_user_by_token(conn,token)
    if not user:
        raise HTTPException(status_code=401, detail="Token non valido")
    return user



def get_cat_id(conn,user_id, name):
    category_id = categories_id_by_name(conn,user_id, name)
    if category_id:
        return category_id
    new_category_id = create_category(conn,user_id, name)
    return new_category_id

def setup_categories_obj(items, status):
    res = {}
    for r in items:
        if r["cat"] not in res: res[r["cat"]] = []
        res[r["cat"]].append({
            "id": r["id"],
            "path": f"/{status}/{r['filename']}" 
        })
    return res

def prepare_image_for_ai(image_path: str, max_size: int = 256) -> str:
    """Ridimensiona e converte in JPEG per ridurre i token"""
    img = Image.open(image_path).convert("RGBA")
    
    # Ridimensiona mantenendo proporzioni
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    
    # Converti su sfondo bianco e salva come JPEG (molto più leggero del PNG)
    background = Image.new("RGB", img.size, (255, 255, 255))
    background.paste(img, mask=img.split()[3])  # usa canale alpha come maschera
    
    buffer = io.BytesIO()
    background.save(buffer, format="JPEG", quality=75)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def image_to_base64_url(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    ext = path.split(".")[-1].lower()
    mime = "image/png" if ext == "png" else "image/jpeg"
    return f"data:{mime};base64,{b64}"