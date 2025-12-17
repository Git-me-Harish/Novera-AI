import google.generativeai as genai
import os

# Get API key from environment or paste directly
API_KEY = os.getenv("GEMINI_API_KEY", "")

genai.configure(api_key=API_KEY)

print("=" * 60)
print("AVAILABLE GEMINI MODELS:")
print("=" * 60)

# List all available models
for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(f"\n✅ {model.name}")
        print(f"   Display Name: {model.display_name}")
        print(f"   Description: {model.description[:100] if model.description else 'N/A'}")
        print(f"   Methods: {model.supported_generation_methods}")

print("\n" + "=" * 60)
print("TESTING MODELS:")
print("=" * 60)

# Try common model names
test_models = [
    "gemini-pro",
    "models/gemini-pro",
    "gemini-1.5-flash-8b",
    "models/gemini-1.5-flash-8b",
    "gemini-2.0-flash-exp",
    "models/gemini-2.0-flash-exp",
]

for model_name in test_models:
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Hello")
        print(f"\n✅ WORKS: {model_name}")
        print(f"   Response: {response.text[:50]}")
    except Exception as e:
        error_msg = str(e)[:100]
        if "404" not in error_msg:
            print(f"\n⚠️  {model_name}: {error_msg}")
