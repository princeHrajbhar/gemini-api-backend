from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.review_routes import router as review_router

app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://*.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex="https://.*\\.vercel\\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(review_router, prefix="/api")


@app.get("/")
def home():
    return {"message": "Sentiment Scraper API running"}