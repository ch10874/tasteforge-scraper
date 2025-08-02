from fastapi import FastAPI
from pydantic import BaseModel
import matinfo
import oda

app = FastAPI()  # Initialize the app

class ProductRequest(BaseModel):
   search_url: str

@app.get("/")  # Test endpoint
async def home():
    return {"message": "Hello World!"}

@app.post("/matinfo")  # Matinfo scraper endpoint
async def matinfo_scraper(request_data: ProductRequest):
    product_data = matinfo.matinfo_scraper(request_data.search_url)
    return {"data": product_data}

@app.post("/oda") # Oda scraper endpoint
async def oda_scraper():
    product_data = oda.oda_scraper()
    return {"data": product_data}
