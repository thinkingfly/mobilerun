"""LangGraph 辅助工具。"""

import os

import httpx

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "") or "sk-sp-e2a147ef4ed54e7991e184b24913f3a8"
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.7-plus")


def call_llm(prompt: str, max_tokens: int = 512) -> str:
    """同步调用 LLM。"""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }

    with httpx.Client(base_url=LLM_BASE_URL, timeout=30) as client:
        resp = client.post("/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
