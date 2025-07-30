from fastapi import FastAPI
import matinfo

app = FastAPI()  # Initialize the app

@app.get("/")  # Test endpoint
async def home():
    return {"message": "Hello World!"}

@app.post("/matinfo")  # Matinfo scraper endpoint
async def matinfo_scraper():
    product_data = matinfo.matinfo_scraper()
    return {"data": product_data}
