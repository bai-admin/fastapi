from fastapi import FastAPI, Path, Query
from typing import Optional
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    price: float

app = FastAPI()

@app.get("/")
async def root():
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI!"}

@app.get("/items/{item_id}")
async def read_item(
    item_id: int = Path(..., description="The ID of the item to get"),
    q: Optional[str] = Query(None, description="Optional query string")
):
    return {"item_id": item_id, "q": q}

@app.post("/items/")
async def create_item(item: Item):
    return item