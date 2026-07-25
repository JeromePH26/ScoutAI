import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

def test_single_call():
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    # These appeared in your list_models output
    models = ["gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

    for m in models:
        print(f"\n--- Testing Model: {m} ---")
        try:
            response = client.models.generate_content(
                model=m,
                contents="Hello, say 'Test successful'"
            )
            print(f"Success! Response: {response.text}")
            return
        except Exception as e:
            print(f"Failed for {m}: {e}")

if __name__ == "__main__":
    test_single_call()
