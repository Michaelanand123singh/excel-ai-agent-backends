from typing import Optional

from app.core.config import settings


def ask_llm(prompt: str) -> str:
    api_key: Optional[str] = settings.GOOGLE_API_KEY
    model_name = settings.GEMINI_MODEL
    if not api_key:
        # Fallback stub in development if no key configured
        return "STUB: " + prompt[:200]
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        res = model.generate_content(prompt)
        text = getattr(res, "text", None) or (res.candidates[0].content.parts[0].text if getattr(res, "candidates", None) else "")
        return text or ""
    except Exception as e:
        return f"ERROR: {e}"


