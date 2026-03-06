from fastapi import APIRouter
from app.controllers.review_controller import analyze_reviews_controller

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.post("/analyze")
def analyze_reviews(data: dict):

    reviews = data.get("reviews", [])

    return analyze_reviews_controller(reviews)