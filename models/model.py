from pydantic import BaseModel
from typing import List

class UserRegister(BaseModel):
    email: str
    password: str
    name: str

class UserLogin(BaseModel):
    email: str
    password: str

class OutfitSave(BaseModel):
    image: str
    item_ids: List[int]
    category_id: int = None

class ItemDetail(BaseModel):
    item_id: int
    taglia: str = ""
    stile: str = ""   
    tessuto: str = "" 
    colore: str = ""
    descrizione: str = "" 
    preferito: bool = False

class GenerateDescription(BaseModel):
    item_id: int