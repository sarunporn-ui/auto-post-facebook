"""Unified LLM client — dispatches to OpenAI, Anthropic, or Gemini based on
`LLM_PROVIDER` in the environment, so the rest of the app can call `complete()`
without caring which model is behind it.
"""
from __future__ import annotations
import json
import re

from src.config import get_settings


def complete(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return _complete_openai(system_prompt, user_prompt, json_mode)
    if provider == "anthropic":
        return _complete_anthropic(system_prompt, user_prompt, json_mode)
    if provider == "gemini":
        return _complete_gemini(system_prompt, user_prompt, json_mode)
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def extract_json(text: str) -> dict:
    """Best-effort JSON extraction for providers that don't guarantee strict
    JSON output (only OpenAI's json_object mode does)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"LLM did not return parsable JSON: {text[:200]}")
        return json.loads(match.group(0))


def _complete_openai(system_prompt: str, user_prompt: str, json_mode: bool) -> str:
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"} if json_mode else None,
    )
    return response.choices[0].message.content or ""


def _complete_anthropic(system_prompt: str, user_prompt: str, json_mode: bool) -> str:
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    suffix = "\n\nRespond with valid JSON only, no prose, no markdown fences." if json_mode else ""
    message = client.messages.create(
        model=settings.llm_model,
        max_tokens=4096,
        system=system_prompt + suffix,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text")


def _complete_gemini(system_prompt: str, user_prompt: str, json_mode: bool) -> str:
    import google.generativeai as genai

    settings = get_settings()
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.llm_model, system_instruction=system_prompt)
    generation_config = {"response_mime_type": "application/json"} if json_mode else None
    response = model.generate_content(user_prompt, generation_config=generation_config)
    return response.text
