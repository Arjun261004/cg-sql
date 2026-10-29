import os
import json
import time
from pathlib import Path
from google import genai
from google.genai import types

class LLMClient:
    CANDIDATE_MODELS = [
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash"
    ]

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            env_file = Path(__file__).resolve().parent.parent.parent / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        os.environ["GEMINI_API_KEY"] = api_key
                        break
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()

    @staticmethod
    def _extract_text(response) -> str:
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        if hasattr(response, "candidates") and response.candidates:
            parts = []
            for candidate in response.candidates:
                if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            parts.append(part.text)
            if parts:
                return "\n".join(parts).strip()
        return ""

    def generate_json(self, prompt: str, schema: type = None) -> dict:
        """Generates a structured JSON response with model fallback."""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        )
        last_err = None
        for model in self.CANDIDATE_MODELS:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                text = self._extract_text(response)
                if text:
                    return json.loads(text)
            except Exception as e:
                last_err = e
                continue
        print(f"LLM generate_json Error across all models: {last_err}")
        return {}

    def generate_text(self, prompt: str) -> str:
        """Generates plain text with model fallback."""
        last_err = None
        for model in self.CANDIDATE_MODELS:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                text = self._extract_text(response)
                if text:
                    return text
            except Exception as e:
                last_err = e
                continue
        print(f"LLM generate_text Error across all models: {last_err}")
        raise last_err or RuntimeError("Failed to generate text from LLM across candidate models")

