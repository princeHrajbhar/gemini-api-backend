from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import json
import re
import time
from typing import List, Dict, Any, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiClient:
    """Client to interact with Gemini for sentiment analysis"""
    
    def __init__(self, headless: bool = False):
        """
        Initialize Gemini client
        
        Args:
            headless: Run browser in headless mode (no GUI)
        """
        self.gemini_url = "https://gemini.google.com/app/b61306bac4a2c500"
        self.headless = headless
        self.driver = None
        
    def _setup_driver(self):
        """Set up Chrome driver with options"""
        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        
        try:
            self.driver = webdriver.Chrome(options=options)
            logger.info("Chrome driver initialized successfully")
        except WebDriverException as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise
    
    def _create_prompt(self, reviews: List[Dict[str, Any]], movie_name: str) -> str:
        """Create the prompt for Gemini"""
        prompt = f"""Based on these movie reviews for "{movie_name}", please provide a JSON analysis with the following structure:
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

Here are the reviews:
{json.dumps(reviews, indent=2)}

Please return ONLY the JSON object with no additional text or explanation."""
        return prompt
    
    def _extract_json_from_response(self, response_text: str) -> Optional[Dict]:
        """Extract JSON from Gemini response"""
        
        # Method 1: Find complete JSON by balancing braces
        def extract_complete_json(text):
            stack = []
            start_index = -1
            
            for i, char in enumerate(text):
                if char == '{':
                    if not stack:
                        start_index = i
                    stack.append(char)
                elif char == '}':
                    if stack:
                        stack.pop()
                        if not stack and start_index != -1:
                            return text[start_index:i+1]
            return None
        
        # Try method 1
        complete_json_str = extract_complete_json(response_text)
        if complete_json_str:
            try:
                return json.loads(complete_json_str)
            except json.JSONDecodeError:
                pass
        
        # Method 2: Find JSON between triple backticks
        json_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        json_blocks = re.findall(json_block_pattern, response_text, re.DOTALL)
        
        for block in json_blocks:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
        
        # Method 3: Try to parse the entire response
        try:
            cleaned = re.sub(r'```json|```', '', response_text).strip()
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Could not parse JSON from response")
            return None
    
    def analyze_sentiment(self, reviews: List[Dict[str, Any]], movie_name: str = "Movie") -> Optional[Dict]:
        """
        Analyze sentiment of reviews using Gemini
        
        Args:
            reviews: List of review dictionaries with 'text' and optional 'rating'
            movie_name: Name of the movie being reviewed
            
        Returns:
            Dictionary with sentiment analysis or None if failed
        """
        try:
            # Set up driver
            self._setup_driver()
            
            # Open Gemini page
            logger.info("Opening Gemini page...")
            self.driver.get(self.gemini_url)
            
            # Wait for input field
            wait = WebDriverWait(self.driver, 10)
            input_field = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[contenteditable='true']"))
            )
            
            # Create and send prompt
            prompt = self._create_prompt(reviews, movie_name)
            logger.info(f"Sending prompt with {len(reviews)} reviews...")
            
            input_field.click()
            input_field.send_keys(prompt)
            input_field.send_keys(Keys.RETURN)
            
            # Wait for response
            logger.info("Waiting for Gemini response...")
            response_selector = "div.markdown.markdown-main-panel"
            response_element = WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, response_selector))
            )
            
            # Allow time for full response
            time.sleep(3)
            
            # Extract response text
            response_text = response_element.text
            logger.info("Response received, extracting JSON...")
            
            # Parse JSON
            result = self._extract_json_from_response(response_text)
            
            if result:
                logger.info("Successfully parsed sentiment analysis")
                return result
            else:
                logger.error("Failed to parse JSON from response")
                return None
                
        except TimeoutException as e:
            logger.error(f"Timeout waiting for element: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
        finally:
            # Clean up
            if self.driver:
                self.driver.quit()
                logger.info("Browser closed")