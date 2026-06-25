"""
LLM Service – uses Groq (OpenAI-compatible API) for fast inference.
Falls back to a mock response if no API key is configured.
"""
import asyncio

from app.core.config import settings

_MOCK_RESPONSE = (
    "[MOCK RESPONSE] Groq API key not configured. "
    "Set GROQ_API_KEY in your .env file to enable real LLM responses. "
    "This is a simulated response for governance demonstration purposes."
)

# Groq models available (for reference)
GROQ_MODELS = [
    "llama-3.3-70b-versatile",   # Best quality, 128k context
    "llama-3.1-8b-instant",       # Fastest, lowest latency
    "mixtral-8x7b-32768",         # Strong 32k context window
    "gemma2-9b-it",               # Efficient, good quality
]


async def complete(prompt: str, model: str | None = None) -> tuple[str, int]:
    """Return (response_text, tokens_used).

    Uses Groq's OpenAI-compatible endpoint with the openai SDK.
    Model defaults to settings.GROQ_MODEL if not specified.
    """
    chosen_model = model or settings.GROQ_MODEL

    if not settings.GROQ_API_KEY:
        await asyncio.sleep(0.05)
        return _MOCK_RESPONSE, 0

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url=settings.GROQ_BASE_URL,
        )
        resp = await client.chat.completions.create(
            model=chosen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.7,
        )
        text = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        return text, tokens

    except Exception as e:
        return f"[GROQ ERROR] {str(e)}", 0
