import os
from google import genai
from dotenv import load_dotenv
import traceback

load_dotenv()

def test_single_call():
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    # Test models in order
    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.5-flash"]

    for m in models:
        print(f"\n--- Testing Model: {m} ---")
        try:
            response = client.models.generate_content(
                model=m,
                contents="Hello, say 'Test successful'"
            )
            print(f"Success! Response: {response.text}")
            return # Stop if one works
        except Exception as e:
            print(f"Failed for {m}:")
            print(f"Error Type: {type(e)}")
            print(f"Error Message: {e}")
            # print(traceback.format_exc())

if __name__ == "__main__":
    test_single_call()
