import google.generativeai as genai
import os


def main() -> None:
    """Print available Gemini generation models when invoked explicitly."""
    genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
    print("Available models for generateContent:")
    print("-" * 50)
    for model in genai.list_models():
        if "generateContent" in model.supported_generation_methods:
            print(f"✓ {model.name}")
            print(f"  Display: {model.display_name}")
            print(f"  Description: {model.description[:100] if model.description else 'N/A'}")
            print()


if __name__ == "__main__":
    main()
