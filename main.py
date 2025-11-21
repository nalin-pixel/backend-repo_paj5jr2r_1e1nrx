import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import List, Optional
import requests

from database import db, create_document, get_documents
from schemas import Product, Message

app = FastAPI(title="momtobe API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"name": "momtobe", "message": "API running"}


def _seed_products_if_empty():
    try:
        if db is None:
            return
        count = db["product"].count_documents({})
        if count == 0:
            sample_products = [
                {
                    "title": "Комфортное платье для будущих мам",
                    "description": "Мягкое трикотажное платье с растущей талией.",
                    "price": 59.99,
                    "category": "Платья",
                    "in_stock": True,
                    "image_url": "https://images.unsplash.com/photo-1556898578-c07eaed1f7f7?q=80&w=1200&auto=format&fit=crop",
                    "sizes": ["S", "M", "L", "XL"],
                    "is_featured": True,
                },
                {
                    "title": "Джинсы для беременных",
                    "description": "Эластичный пояс, удобная посадка и прочная ткань.",
                    "price": 69.99,
                    "category": "Джинсы",
                    "in_stock": True,
                    "image_url": "https://images.unsplash.com/photo-1515378791036-0648a3ef77b2?q=80&w=1200&auto=format&fit=crop",
                    "sizes": ["S", "M", "L"],
                    "is_featured": True,
                },
                {
                    "title": "Футболка Basic",
                    "description": "Дышащий хлопок, свободный крой для живота.",
                    "price": 24.99,
                    "category": "Топы",
                    "in_stock": True,
                    "image_url": "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?q=80&w=1200&auto=format&fit=crop",
                    "sizes": ["S", "M", "L", "XL"],
                    "is_featured": False,
                },
                {
                    "title": "Теплый кардиган",
                    "description": "Мягкий оверсайз-кардиган на осень и зиму.",
                    "price": 89.0,
                    "category": "Верхняя одежда",
                    "in_stock": True,
                    "image_url": "https://images.unsplash.com/photo-1515378791036-0648a3ef77b2?q=80&w=1200&auto=format&fit=crop",
                    "sizes": ["M", "L"],
                    "is_featured": False,
                },
            ]
            for p in sample_products:
                try:
                    create_document("product", Product(**p))
                except Exception:
                    # Ignore individual failures while seeding
                    pass
    except Exception:
        pass


@app.get("/api/products", response_model=List[Product])
def list_products(category: Optional[str] = None, featured: Optional[bool] = None):
    """List products with optional filters. Seeds defaults if collection empty."""
    _seed_products_if_empty()
    filt = {}
    if category:
        filt["category"] = category
    if featured is not None:
        filt["is_featured"] = featured
    try:
        items = get_documents("product", filt)
        products: List[Product] = []
        for d in items:
            d.pop("_id", None)
            products.append(Product(**d))
        return products
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ContactRequest(BaseModel):
    name: str
    email: str
    message: str


@app.post("/api/contact")
def contact(data: ContactRequest):
    try:
        msg = Message(**data.model_dump())
        _id = create_document("message", msg)
        return {"status": "ok", "id": _id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/proxy-image")
def proxy_image(url: str = Query(..., description="Absolute image URL to proxy")):
    """Proxy external images to avoid hotlink protection, CORS/referrer issues.
    Adds simple caching headers.
    """
    try:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(status_code=400, detail="Invalid URL")
        # Fetch the image
        resp = requests.get(url, stream=True, timeout=10, headers={
            "User-Agent": "momtobe-proxy/1.0 (+https://example.com)",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": ""
        })
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        if not resp.ok:
            raise HTTPException(status_code=404, detail="Image not found")

        def iter_content():
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        headers = {
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        }
        return StreamingResponse(iter_content(), media_type=content_type, headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        return Response(status_code=502, content=str(e))


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
