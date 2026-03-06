from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import logging
import json
import time
import re


# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


GEMINI_URL = "https://gemini.google.com/app/"


# ---------------- CHROME OPTIONS ----------------
logger.info("Initializing Chrome options")

options = Options()
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

options.page_load_strategy = "eager"

# disable images
prefs = {"profile.managed_default_content_settings.images": 2}
options.add_experimental_option("prefs", prefs)


# ---------------- START DRIVER ----------------
logger.info("Starting Chrome driver")

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 30)

logger.info("Opening Gemini page")

driver.get(GEMINI_URL)

logger.info("Gemini page loaded")


# ---------------- JSON EXTRACTION ----------------
def extract_complete_json(text):

    logger.info("Extracting JSON from response")

    try:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start != -1 and end != -1:
            json_string = text[start:end]
            return json.loads(json_string)

    except Exception as e:
        logger.warning(f"Primary JSON parse failed: {e}")

    # fallback for ```json blocks
    try:

        pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        matches = re.findall(pattern, text, re.DOTALL)

        for m in matches:
            return json.loads(m)

    except Exception as e:
        logger.warning(f"Fallback JSON parse failed: {e}")

    return None


# ---------------- RESPONSE WAIT ----------------
def wait_for_complete_response(element):

    logger.info("Waiting for Gemini streaming to finish")

    prev_text = ""

    for _ in range(30):

        current_text = element.text.strip()

        if current_text == prev_text and len(current_text) > 50:
            logger.info("Gemini response stabilized")
            return current_text

        prev_text = current_text
        time.sleep(1)

    logger.warning("Response stabilization timeout")

    return element.text


# ---------------- MAIN SERVICE ----------------
def analyze_reviews_service(reviews: list):

    start_time = time.time()

    logger.info("Starting review analysis")

    question = f"""
Based on these movie reviews, provide JSON analysis with structure:

{{
  "overallSentiment": "positive | neutral | negative",
  "score": number between 0 and 1,
  "positivePercentage": number,
  "neutralPercentage": number,
  "negativePercentage": number,
  "summary": "5-10 sentence summary",
  "strengths": ["point1", "point2"],
  "weaknesses": ["point1", "point2"],
  "emotionalTone": "tone"
}}

Reviews:
{json.dumps(reviews, indent=2)}

Return ONLY JSON object.
"""

    try:

        logger.info("Locating Gemini input field")

        input_field = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[contenteditable='true']"))
        )

        logger.info("Input field found")

        input_field.click()

        logger.info("Injecting prompt via JS (fast)")

        driver.execute_script(
            "arguments[0].innerText = arguments[1];",
            input_field,
            question
        )

        logger.info("Submitting prompt")

        input_field.send_keys(Keys.ENTER)

        logger.info("Waiting for Gemini response")

        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.markdown.markdown-main-panel"))
        )

        response_elements = driver.find_elements(
            By.CSS_SELECTOR,
            "div.markdown.markdown-main-panel"
        )

        response_element = response_elements[-1]

        logger.info("Response element detected")

        response_text = wait_for_complete_response(response_element)

        logger.info("Gemini raw response:")
        logger.info(response_text)

        parsed_json = extract_complete_json(response_text)

        if parsed_json:

            elapsed = round(time.time() - start_time, 2)

            logger.info(f"Analysis completed in {elapsed}s")

            return parsed_json

        logger.error("JSON parsing failed")

        return {
            "status": "error",
            "message": "Could not parse Gemini response",
            "raw": response_text
        }

    except TimeoutException:

        logger.error("Gemini response timeout")

        return {
            "status": "error",
            "message": "Gemini response timeout"
        }


# ---------------- SHUTDOWN ----------------
def close_driver():

    logger.info("Closing Chrome driver")

    driver.quit()