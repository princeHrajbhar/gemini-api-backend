from app.services.gemini_service import analyze_reviews_service


def analyze_reviews_controller(reviews):

    result = analyze_reviews_service(reviews)

    return result