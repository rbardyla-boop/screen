"""Shared AI provider abstraction — ollama / openai / claude.

Single source of truth for ask_ai(). Import this everywhere.

## Provider config (.env)

  AI_PROVIDER       = ollama | openai | claude    (default: ollama)

## Per-tier model overrides

Tasks are bucketed into three tiers. Each tier can use a different model so
cheap tasks don't pay for heavy models and heavy tasks don't get starved.

  Tier      | What uses it                            | Claude default     | Ollama default
  --------- | --------------------------------------- | ------------------ | ------------------
  light     | inbox classify, graph bridge note       | claude-haiku-4-5   | gemma3:12b
  standard  | link, gaps, skills, ask, write-prep     | claude-haiku-4-5   | gemma3:12b
  heavy     | daily synthesis, contradict, synthesize | claude-sonnet-4-6  | gemma3:12b

Override any tier via .env:
  CLAUDE_LIGHT_MODEL    (default: claude-haiku-4-5)
  CLAUDE_STANDARD_MODEL (default: claude-haiku-4-5)
  CLAUDE_HEAVY_MODEL    (default: claude-sonnet-4-6)
  OLLAMA_LIGHT_MODEL    (default: gemma3:12b)
  OLLAMA_STANDARD_MODEL (default: gemma3:12b)
  OLLAMA_HEAVY_MODEL    (default: gemma3:12b)
  OPENAI_LIGHT_MODEL    (default: gpt-4o-mini)
  OPENAI_STANDARD_MODEL (default: gpt-4o-mini)
  OPENAI_HEAVY_MODEL    (default: gpt-4o)

## Cost reference (Claude, as of 2026)
  Haiku 4.5:  $0.80/M in,  $4/M out  — daily synthesis ≈ $0.013/run
  Sonnet 4.6: $3/M in,    $15/M out  — contradict/synthesize ≈ $0.05/run

## Why gemma3:12b instead of qwen2.5:3b for local
  qwen2.5:3b has a ~4096 token effective context. The daily synthesis prompt
  sends 26k chars (~8.5k tokens) of OCR — the model silently truncates most
  of your day. gemma3:12b has 128k context and much stronger reasoning.
  Both are already installed on this machine.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

AI_PROVIDER: str = os.environ.get("AI_PROVIDER", "ollama")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")

# Per-tier model selection — override in .env as needed
_CLAUDE_MODELS = {
    "light":    os.environ.get("CLAUDE_LIGHT_MODEL",    "claude-haiku-4-5"),
    "standard": os.environ.get("CLAUDE_STANDARD_MODEL", "claude-haiku-4-5"),
    "heavy":    os.environ.get("CLAUDE_HEAVY_MODEL",    "claude-sonnet-4-6"),
}
_OLLAMA_MODELS = {
    "light":    os.environ.get("OLLAMA_LIGHT_MODEL",    "gemma3:12b"),
    "standard": os.environ.get("OLLAMA_STANDARD_MODEL", "gemma3:12b"),
    "heavy":    os.environ.get("OLLAMA_HEAVY_MODEL",    "gemma3:12b"),
}
_OPENAI_MODELS = {
    "light":    os.environ.get("OPENAI_LIGHT_MODEL",    "gpt-4o-mini"),
    "standard": os.environ.get("OPENAI_STANDARD_MODEL", "gpt-4o-mini"),
    "heavy":    os.environ.get("OPENAI_HEAVY_MODEL",    "gpt-4o"),
}

# Legacy single-model env vars still respected as tier overrides
# so existing .env files with OLLAMA_MODEL=qwen2.5:3b keep working.
_legacy_ollama = os.environ.get("OLLAMA_MODEL")
if _legacy_ollama:
    for _t in _OLLAMA_MODELS:
        _OLLAMA_MODELS[_t] = _OLLAMA_MODELS.get(_t) or _legacy_ollama

_legacy_claude = os.environ.get("CLAUDE_MODEL")
if _legacy_claude:
    for _t in _CLAUDE_MODELS:
        _CLAUDE_MODELS[_t] = _CLAUDE_MODELS.get(_t) or _legacy_claude

_legacy_openai = os.environ.get("OPENAI_MODEL")
if _legacy_openai:
    for _t in _OPENAI_MODELS:
        _OPENAI_MODELS[_t] = _OPENAI_MODELS.get(_t) or _legacy_openai


def ask_ai(prompt: str, tier: str = "standard") -> str:
    """Send prompt to the configured AI provider and return the response text.

    Args:
        prompt: The full prompt string.
        tier:   "light" | "standard" | "heavy" — selects model complexity.
                Use "light" for simple classification.
                Use "standard" for most tasks.
                Use "heavy" for synthesis over large context (daily report,
                contradict, synthesize).
    """
    if tier not in ("light", "standard", "heavy"):
        tier = "standard"

    if AI_PROVIDER == "ollama":
        model = _OLLAMA_MODELS[tier]
        try:
            res = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=300,
            )
            return res.json().get("response", "").strip()
        except Exception as e:
            return f"Ollama error ({model}): {e}"

    elif AI_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            return "OPENAI_API_KEY not set in .env"
        model = _OPENAI_MODELS[tier]
        try:
            res = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            return res.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"OpenAI error ({model}): {e}"

    elif AI_PROVIDER == "claude":
        if not ANTHROPIC_API_KEY:
            return "ANTHROPIC_API_KEY not set in .env"
        try:
            import anthropic  # lazy — only loaded when AI_PROVIDER=claude
        except ImportError:
            return "anthropic package not installed. Run: pip install anthropic"
        model = _CLAUDE_MODELS[tier]
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            return f"Claude API error ({model}): {e}"

    return f"Unknown AI_PROVIDER: {AI_PROVIDER!r}"
