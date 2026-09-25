from fastapi import FastAPI

from app.routes.founders import router as founders_router
from app.routes.startups import router as startup_router

app = FastAPI(title="1435 Capital — Founder Evidence Graph")

app.include_router(startup_router)
app.include_router(founders_router)


@app.get("/")
def home():
    return {"message": "1435 Capital API is running"}
