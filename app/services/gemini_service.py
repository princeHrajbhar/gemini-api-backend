from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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


GEMINI_URL = "https://gemini.google.com/app"


# ---------------- CHROME OPTIONS ----------------
logger.info("Initializing Chrome options")

options = Options()
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--window-size=1920,1080")

# Remove eager loading strategy as it can cause issues
# options.page_load_strategy = "eager"

# disable images and unnecessary resources
prefs = {
    "profile.managed_default_content_settings.images": 2,
    "profile.default_content_setting_values.notifications": 2,
    "profile.managed_default_content_settings.stylesheets": 2,
    "profile.managed_default_content_settings.cookies": 2,
    "profile.managed_default_content_settings.javascript": 1,  # Keep JS enabled
    "profile.managed_default_content_settings.plugins": 2,
    "profile.managed_default_content_settings.popups": 2,
    "profile.managed_default_content_settings.geolocation": 2,
    "profile.managed_default_content_settings.media_stream": 2,
}
options.add_experimental_option("prefs", prefs)

# Add additional arguments for better performance in AWS
options.add_argument("--disable-setuid-sandbox")
options.add_argument("--disable-extensions")
options.add_argument("--disable-accelerated-2d-canvas")
options.add_argument("--proxy-server='direct://'")
options.add_argument("--proxy-bypass-list=*")
options.add_argument("--disable-web-security")
options.add_argument("--ignore-certificate-errors")
options.add_argument("--ignore-ssl-errors")


# ---------------- START DRIVER ----------------
logger.info("Starting Chrome driver")

driver = webdriver.Chrome(options=options)
# Increase timeout for AWS environment
wait = WebDriverWait(driver, 60)  # Increased from 30 to 60 seconds

logger.info("Opening Gemini page")

try:
    driver.get(GEMINI_URL)
    logger.info("Waiting for page to load completely...")
    
    # Wait for body to be present
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    
    # Additional wait for dynamic content
    time.sleep(5)  # Give extra time for JS to initialize
    
    logger.info("Gemini page loaded")
except TimeoutException as e:
    logger.error(f"Failed to load Gemini page: {e}")
    driver.quit()
    raise


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
    stable_count = 0
    required_stable_iterations = 3  # Require 3 consecutive stable reads

    for i in range(45):  # 45 seconds timeout
        try:
            current_text = element.text.strip()
            
            if current_text and len(current_text) > 50:
                if current_text == prev_text:
                    stable_count += 1
                    if stable_count >= required_stable_iterations:
                        logger.info(f"Gemini response stabilized after {i+1}s")
                        return current_text
                else:
                    stable_count = 0  # Reset if text changed
                
                prev_text = current_text
            else:
                logger.debug(f"Response too short or empty ({len(current_text) if current_text else 0} chars)")
        except Exception as e:
            logger.warning(f"Error reading response: {e}")
        
        time.sleep(1)

    logger.warning("Response stabilization timeout")
    return element.text if element else ""


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

        # Try multiple selectors for the input field
        input_selectors = [
            "div[contenteditable='true']",
            "div.ql-editor[contenteditable='true']",
            "div[role='textbox']",
            "div[data-testid='chat-input']"
        ]
        
        input_field = None
        for selector in input_selectors:
            try:
                input_field = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.info(f"Input field found with selector: {selector}")
                break
            except TimeoutException:
                continue
        
        if not input_field:
            # Try to find any editable div as fallback
            input_field = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[contenteditable='true']"))
            )

        logger.info("Input field found")

        # Clear any existing text
        try:
            input_field.clear()
        except:
            driver.execute_script("arguments[0].innerHTML = '';", input_field)

        logger.info("Injecting prompt via JS")
        
        # Try multiple methods to set text
        try:
            driver.execute_script(
                "arguments[0].innerText = arguments[1];",
                input_field,
                question
            )
        except:
            # Fallback: send keys
            input_field.send_keys(question)

        # Small delay before submitting
        time.sleep(1)

        logger.info("Submitting prompt")
        input_field.send_keys(Keys.ENTER)

        logger.info("Waiting for Gemini response")

        # Wait for response to appear with multiple selectors
        response_selectors = [
            "div.markdown.markdown-main-panel",
            "div.response-container",
            "div[data-testid='response-content']",
            "div.message-content"
        ]
        
        response_element = None
        for selector in response_selectors:
            try:
                wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                response_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if response_elements:
                    response_element = response_elements[-1]
                    logger.info(f"Response element found with selector: {selector}")
                    break
            except:
                continue

        if not response_element:
            # Fallback: try to find any element with substantial text
            all_elements = driver.find_elements(By.CSS_SELECTOR, "div")
            for elem in all_elements:
                text = elem.text.strip()
                if len(text) > 100 and "{" in text and "}" in text:
                    response_element = elem
                    logger.info("Response element found via text fallback")
                    break

        if not response_element:
            raise Exception("Could not find response element")

        logger.info("Response element detected")

        response_text = wait_for_complete_response(response_element)

        logger.info("Gemini raw response:")
        logger.info(response_text[:500] + "..." if len(response_text) > 500 else response_text)

        parsed_json = extract_complete_json(response_text)

        if parsed_json:
            elapsed = round(time.time() - start_time, 2)
            logger.info(f"Analysis completed in {elapsed}s")
            return parsed_json

        logger.error("JSON parsing failed")
        
        # Try to salvage partial JSON
        try:
            # Look for any JSON-like structure
            json_match = re.search(r'\{[^{}]*\}', response_text)
            if json_match:
                partial_json = json.loads(json_match.group())
                return partial_json
        except:
            pass

        return {
            "status": "error",
            "message": "Could not parse Gemini response",
            "raw": response_text[:500]  # Limit raw response size
        }

    except TimeoutException as e:
        logger.error(f"Gemini response timeout: {e}")
        return {
            "status": "error",
            "message": "Gemini response timeout - service may be slow"
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "status": "error",
            "message": f"Analysis failed: {str(e)}"
        }


# ---------------- SHUTDOWN ----------------
def close_driver():
    logger.info("Closing Chrome driver")
    driver.quit()