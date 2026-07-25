import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

def list_available_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env")
        return

    client = genai.Client(api_key=api_key)
    print("Listing available models:")
    try:
        for model in client.models.list():
            print(f"Name: {model.name}, Supported Actions: {model.supported_actions}")
    except Exception as e:
        print(f"Failed to list models: {e}")

if __name__ == "__main__":
    list_available_models()
