import sqlite3
import os
import secrets
from fastapi import HTTPException
import hashlib

def generate_new_token():
    raw_token = secrets.token_hex(32)
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, hashed


def _get_connection():
    """Connessione diretta, da usare internamente"""
    conn = sqlite3.connect(os.getenv("DB_NAME", "wardrobe_v3.db"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def get_db():
    """Dependency per FastAPI (Depends)"""
    conn = _get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = _get_connection() 
    cursor = conn.cursor()
    # Tabella Utenti
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        token TEXT)''')
    # Tabella Categorie (legate a utente)
    cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)''')
    # Tabella Capi
    cursor.execute('''CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE)''')
    # Tabella Outfit
    cursor.execute('''CREATE TABLE IF NOT EXISTS outfits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        category_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES outfit_categories(id) ON DELETE SET NULL)''')
    # Tabella Ponte Outfit-Items
    cursor.execute('''CREATE TABLE IF NOT EXISTS outfit_items (
        outfit_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        FOREIGN KEY(outfit_id) REFERENCES outfits(id) ON DELETE CASCADE,
        FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE,
        PRIMARY KEY (outfit_id, item_id))''')
    # Tabella Dettaglio item
    cursor.execute('''CREATE TABLE IF NOT EXISTS items_detail (
        item_id INTEGER PRIMARY KEY,
        taglia TEXT,
        stile TEXT,
        tessuto TEXT,
        colore TEXT DEFAULT '',
        descrizione TEXT DEFAULT '',
        preferito INTEGER DEFAULT 0,
        FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE)''')
    # Tabella Categorie Outfit (opzionale, per organizzare outfit in categorie)
    cursor.execute('''CREATE TABLE IF NOT EXISTS outfit_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)''')
    # Tabella stili ammessi
    cursor.execute('''CREATE TABLE IF NOT EXISTS stili_ammessi (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL)''')
    # Tabella tessuti ammessi
    cursor.execute('''CREATE TABLE IF NOT EXISTS tessuti_ammessi (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL)''')
    # Tabella colori ammessi
    cursor.execute('''CREATE TABLE IF NOT EXISTS colori_ammessi (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL)''')
    # Popolamento iniziale (INSERT OR IGNORE per non duplicare a ogni restart)
    _default_stili   = ["Sera", "Giorno", "Casual", "Elegante", "Sportivo"]
    _default_tessuti = ["Lana", "Cotone", "Lino", "Jeans", "Seta"]
    _default_colori  = [
        "Bianco", "Nero", "Grigio", "Rosso", "Rosa", "Arancio",
        "Giallo", "Verde", "Turchese", "Blu", "Blu Navy",
        "Viola", "Marrone", "Beige"
    ]
 
    cursor.executemany(
        "INSERT OR IGNORE INTO stili_ammessi (name) VALUES (?)",
        [(s,) for s in _default_stili]
    )
    cursor.executemany(
        "INSERT OR IGNORE INTO tessuti_ammessi (name) VALUES (?)",
        [(t,) for t in _default_tessuti]
    )
    cursor.executemany(
        "INSERT OR IGNORE INTO colori_ammessi (name) VALUES (?)",
        [(c,) for c in _default_colori]
    )
 
    conn.commit()
    conn.close()


def register_user(conn, email, password, name):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (email, password, name) VALUES (?, ?, ?)", (email, password, name))
        conn.commit()
        user_id = cursor.lastrowid
        # Crea categoria outfit di default
        cursor.execute("INSERT INTO outfit_categories (user_id, name) VALUES (?, ?)", (user_id, "GEN IA"))
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None


def get_user_by_email(conn, email):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
    except Exception as e:
        print(f"Error fetching user by email {email}: {e}")
        return None

    return user

def get_user_by_token(conn, raw_token: str):
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE token = ?", (hashed,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching user by token: {e}")
        return None



def update_user_token(conn, user_id):
    raw_token, hashed_token = generate_new_token()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET token = ? WHERE id = ?", (hashed_token, user_id))
        conn.commit()
    except Exception as e:
        print(f"Error updating token for user {user_id}: {e}")
        return None, None

    return raw_token 


#CATEGORIE
def categories_id_by_name(conn, user_id, name):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM categories WHERE user_id=? AND name=?", (user_id, name))
        category = cursor.fetchone()
        if category:
            return category["id"]
    except Exception as e:
        print(f"Error fetching category id for user {user_id} and name {name}: {e}")
        return None

    return None

def get_category_by_user(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name FROM categories WHERE user_id=?", (user_id,))
        category = cursor.fetchall()
        return category or []
    except Exception as e:
        print(f"Error fetching category name for user {user_id}: {e}")
        return None


def create_category(conn, user_id, name):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categories (user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
        return {"id": cursor.lastrowid, "name": name}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Categoria già esistente")


def update_item_category(conn, item_id, user, new_category):
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE items SET category_id=? WHERE id=? AND user_id=?",
                    (new_category, item_id, user["id"]))  # ← aggiunto user_id per sicurezza
        conn.commit()
    except Exception as e:
        print(f"Error updating item category for item {item_id}: {e}")

        
# ITEMS
def create_item(conn, user, category_id, filename, status):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO items (user_id, category_id, filename, status) VALUES (?, ?, ?, ?)",(user["id"], category_id, filename, status))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error creating item for user {user['id']}: {e}")
        return None


def get_item_by_user_status(conn, user_id, status):
    cursor = conn.cursor()
    try:
        cursor.execute('''SELECT items.id, items.filename, categories.name as cat FROM items 
                          JOIN categories ON items.category_id = categories.id 
                          WHERE items.status=? AND items.user_id=?''', (status, user_id))
        items = cursor.fetchall()
        print(f"Fetched {len(items)} items for user {user_id} with status {status}")
    except Exception as e:
        print(f"Error fetching items for user {user_id}: {e}")
        return None

    return items

def update_item_status(conn, item_id, filename, new_status):
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE items SET status=? WHERE id=? AND filename=?", (new_status, item_id, filename))
        conn.commit()
    except Exception as e:
        print(f"Error updating item status for item {item_id}: {e}")
        return None

        
def get_item_by_id(conn, item_id):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT items.*, categories.name as cat FROM items JOIN categories ON items.category_id=categories.id WHERE items.id=?", (item_id,))
        item = cursor.fetchone()
    except Exception as e:
        print(f"Error fetching item by id {item_id}: {e}")
        return None

    return item

def get_bulk_items_by_user(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT items_detail.* FROM items_detail
        JOIN items ON items_detail.item_id = items.id
        WHERE items.user_id = ?
        """, (user_id,))
        items = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching bulk items for user {user_id}: {e}")
        return None

    return items

def get_items_detail_by_id(conn, item_id):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM items_detail WHERE item_id=?", (item_id,))
        item_detail = cursor.fetchone()
    except Exception as e:
        print(f"Error fetching item detail by id {item_id}: {e}")
        return None

    return item_detail

def create_item_detail(conn, item_id, taglia, stile, tessuto, colore, descrizione, preferito):
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO items_detail (item_id, taglia, stile, tessuto, colore, descrizione, preferito)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            taglia=excluded.taglia,
            stile=excluded.stile,
            tessuto=excluded.tessuto,
            colore=excluded.colore,
            descrizione=excluded.descrizione,
            preferito=excluded.preferito
        """, (item_id, taglia, stile, tessuto, colore, descrizione, preferito))
        conn.commit()
    except Exception as e:
        print(f"Error creating item detail for item {item_id}: {e}")


def delete_item(conn, item_id):
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM items WHERE id=?", (item_id,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting item {item_id}: {e}")
        return None

        
# OUTFITS
def create_outfit(conn, user_id, filename, category_id):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO outfits (user_id, filename, category_id) VALUES (?, ?, ?)",(user_id, filename, category_id))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error creating outfit for user {user_id}: {e}")
        return None


def create_outfit_item(conn, outfit_id, item_id):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO outfit_items (outfit_id, item_id) VALUES (?, ?)", (outfit_id, item_id))
        conn.commit()
    except Exception as e:
        print(f"Error creating outfit-item link for outfit {outfit_id} and item {item_id}: {e}")
        return None


def get_outfits_by_user(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute('''SELECT outfits.id, outfits.filename, 
                outfit_categories.name as cat_name,
                outfit_categories.id as cat_id
                FROM outfits 
                LEFT JOIN outfit_categories ON outfits.category_id = outfit_categories.id
                WHERE outfits.user_id=? ORDER BY outfits.id DESC''', (user_id,))
        outfits = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching outfits for user {user_id}: {e}")
        return None

    return outfits

def delete_outfit(conn, outfit_id):
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM outfits WHERE id=?", (outfit_id,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting outfit {outfit_id}: {e}")
        return None


def get_filname_by_outfit_id(conn, outfit_id):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT filename FROM outfits WHERE id=?", (outfit_id,))
        outfit = cursor.fetchone()
        if outfit:
            return outfit
    except Exception as e:
        print(f"Error fetching filename for outfit {outfit_id}: {e}")
        return None

    return None

def get_outfit_by_id_and_user(conn, outfit_id, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM outfits WHERE id=? AND user_id=?", (outfit_id, user_id))
        outfit = cursor.fetchone()
        if outfit:
            return outfit
    except Exception as e:
        print(f"Error fetching outfit {outfit_id} for user {user_id}: {e}")
        return None

    return None

 # OUTFIT CATEGORIES
def get_outfit_categories_by_user(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name FROM outfit_categories WHERE user_id=? ORDER BY name", (user_id,))
        categories = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching outfit categories for user {user_id}: {e}")
        return None

    return categories

def create_new_outfit_category(conn, user_id, name):
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO outfit_categories (user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
        return {"id": cursor.lastrowid, "name": name}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Categoria già esistente")

        
def delete_outfit_category_by_id(conn, category_id, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM outfit_categories WHERE id=? AND user_id=?", (category_id, user_id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        print(f"Error deleting outfit category {category_id}: {e}")
        return None


def get_outfit_category_by_id_and_user(conn, category_id, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name FROM outfit_categories WHERE id=? AND user_id=?", (category_id, user_id))
        category = cursor.fetchone()
        if category:
            return category
    except Exception as e:
        print(f"Error fetching outfit category {category_id} for user {user_id}: {e}")
        return None

    return None

def move_outfit_category(conn, outfit_id, user_id, category_id):
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE outfits SET category_id=? WHERE id=? AND user_id=?", (category_id, outfit_id, user_id))
        conn.commit()
    except Exception as e:
        print(f"Error moving outfit {outfit_id} to category {category_id} for user {user_id}: {e}")
        return None

        
# STATISTICHE
def get_stats(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT categories.name, COUNT(items.id) as count 
        FROM categories
        LEFT JOIN items ON items.category_id = categories.id 
            AND items.status='ready' AND items.user_id=?
        WHERE categories.user_id=?
        GROUP BY categories.id, categories.name
        ORDER BY count DESC
        """, (user_id, user_id))
        category_counts = cursor.fetchall()
        return category_counts
    except Exception as e:
        print(f"Error fetching stats for user {user_id}: {e}")
        return None


def tessuti_piu_usati(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT items_detail.tessuto FROM items_detail
            JOIN items ON items_detail.item_id = items.id
            WHERE items.user_id=? AND items_detail.tessuto != ''
        """, (user_id,))
        tessuti_counts = cursor.fetchall()
        return tessuti_counts
    except Exception as e:
        print(f"Error fetching fabric stats for user {user_id}: {e}")
        return None


def stiles_piu_usati(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT items_detail.stile FROM items_detail
            JOIN items ON items_detail.item_id = items.id
            WHERE items.user_id=? AND items_detail.stile != ''
        """, (user_id,))
        stili_counts = cursor.fetchall()
        return stili_counts
    except Exception as e:
        print(f"Error fetching style stats for user {user_id}: {e}")
        return None


def tot_items(conn, user_id, status):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as tot FROM items WHERE user_id=? AND status=?", (user_id, status))
        count = cursor.fetchone()
        return count["tot"] if count else 0
    except Exception as e:
        print(f"Error fetching total items for user {user_id}: {e}")
        return None

        
def items_preferiti(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT COUNT(*) as tot FROM items_detail 
        JOIN items ON items_detail.item_id = items.id 
        WHERE items.user_id=? AND items_detail.preferito=1
        """, (user_id,))
        count = cursor.fetchone()
        return count["tot"] if count else 0
    except Exception as e:
        print(f"Error fetching favorite items for user {user_id}: {e}")
        return None

        
def capi_mai_usati_in_outfit(conn, user_id, status):
    cursor = conn.cursor()
    try:
        cursor.execute("""
                 SELECT COUNT(*) as tot FROM items
                 WHERE items.user_id=? AND items.status=?
                 AND items.id NOT IN (SELECT DISTINCT item_id FROM outfit_items)
             """, (user_id, status))
        items = cursor.fetchone()
        return items["tot"] if items else 0
    except Exception as e:
        print(f"Error fetching never used items for user {user_id}: {e}")
        return None


def tot_outfit(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as tot FROM outfits WHERE user_id=?", (user_id,))
        outfits = cursor.fetchone()
        return outfits["tot"] if outfits else 0
    except Exception as e:
        print(f"Error fetching total outfits for user {user_id}: {e}")
        return None

        
# AI ANALYSIS
def get_items_for_ai_analysis_by_id(conn, user_id, item_id, status):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT items.filename, categories.name as cat
            FROM items
            JOIN categories ON items.category_id = categories.id
            WHERE items.id=? AND items.user_id=? AND items.status=?
        """, (item_id, user_id, status))
        item = cursor.fetchone()
        return item
    except Exception as e:
        print(f"Error fetching item for AI analysis for user {user_id} and item {item_id}: {e}")
        return None


def get_outfit_category_genai(conn, user_id):
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, name FROM outfit_categories WHERE user_id=? AND name='GEN IA'",
            (user_id,)
        )
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching GEN IA category for user {user_id}: {e}")
        return None
    
# Funzione per ottenere stili, tessuti e colori ammessi (per validazione lato AI)
def get_stili_ammessi(conn) -> list[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM stili_ammessi ORDER BY name")
    return [r["name"] for r in cursor.fetchall()]
 
 
def get_tessuti_ammessi(conn) -> list[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM tessuti_ammessi ORDER BY name")
    return [r["name"] for r in cursor.fetchall()]
 
 
def get_colori_ammessi(conn) -> list[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM colori_ammessi ORDER BY name")
    return [r["name"] for r in cursor.fetchall()]