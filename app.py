import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


AGENT_NAME = "nlip-knowledge-agent"
MODEL_NAME = os.getenv("NLIP_MODEL_NAME", "llama-4-scout")
JETSTREAM_CHAT_URL = os.getenv("JETSTREAM_CHAT_URL", "")
JETSTREAM_API_KEY = os.getenv("JETSTREAM_API_KEY", "")
CONFIDENTIAL_AGENT_URL = os.getenv("CONFIDENTIAL_AGENT_URL", "")
KNOWLEDGE_BASE_PATH = Path(os.getenv("KNOWLEDGE_BASE_PATH", "data/knowledge_base.json"))


class NLIPMessage(BaseModel):
    messageType: str | None = None
    format: str
    subformat: str
    content: Any
    submessages: list[dict[str, Any]] = Field(default_factory=list)


app = FastAPI(title="NLIP Knowledge Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def nlip_response(content: Any, subformat: str = "json") -> dict[str, Any]:
    return {
        "messageType": "response",
        "format": "json",
        "subformat": subformat,
        "content": content,
    }


def extract_query(message: NLIPMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    if isinstance(message.content, dict):
        for key in ("query", "prompt", "text"):
            value = message.content.get(key)
            if isinstance(value, str):
                return value
    raise HTTPException(
        status_code=400,
        detail="NLIP content must be text or a JSON object with query/prompt/text.",
    )


def load_knowledge_base() -> list[dict[str, Any]]:
    if not KNOWLEDGE_BASE_PATH.exists():
        return []
    return json.loads(KNOWLEDGE_BASE_PATH.read_text())


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9-]+", text.lower()))


def retrieve(query: str, limit: int = 4) -> list[dict[str, Any]]:
    query_terms = tokenize(query)
    if not query_terms:
        return []

    scored = []
    for item in load_knowledge_base():
        text = item.get("text", "")
        terms = tokenize(text)
        score = len(query_terms & terms) / max(1, len(query_terms))
        if score:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, item in scored[:limit]:
        result = dict(item)
        result["score"] = score
        results.append(result)
    return results


def ask_llm(query: str, contexts: list[dict[str, Any]]) -> str | None:
    if not JETSTREAM_CHAT_URL:
        return None

    context_text = "\n\n".join(
        f"Source: {item.get('source', 'unknown')}\n{item.get('text', '')}"
        for item in contexts
    )
    prompt = (
        "You are an NLIP knowledge assistant. NLIP means Natural Language "
        "Interaction Protocol. Answer the user's NLIP question using the provided sources. "
        "If the sources are insufficient, say so. Include source names when useful.\n\n"
        f"Sources:\n{context_text}\n\nQuestion: {query}\n\nAnswer:"
    )
    if "chat/completions" in JETSTREAM_CHAT_URL:
        body = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": "You are an NLIP knowledge assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 400,
        }
    else:
        body = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "temperature": 0.1,
            "max_tokens": 180,
            "stop": ["\nThe answer", "\nThe question", "\nWe need", "\n\nThe user", "assistantfinal"],
        }
    headers = {"Content-Type": "application/json"}
    if JETSTREAM_API_KEY:
        headers["Authorization"] = f"Bearer {JETSTREAM_API_KEY}"

    req = urllib.request.Request(
        JETSTREAM_CHAT_URL,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))

    choice = payload["choices"][0]
    if "message" in choice:
        answer = choice["message"]["content"]
    else:
        answer = choice.get("text", "").strip()

    for marker in ("assistantfinal", "assistant final", "Final answer:"):
        if marker in answer:
            answer = answer.split(marker, 1)[1].strip()

    if "\n\n" in answer and answer.lower().startswith("the user asks"):
        answer = answer.split("\n\n", 1)[1].strip()

    for starter in ("NLIP stands", "NLIP, or", "Natural Language Interaction Protocol"):
        idx = answer.find(starter)
        if idx > 0:
            answer = answer[idx:].strip()
            break

    for bad_tail in (
        "\n```",
        "```json",
        "\nThe answer",
        "\nThe question",
        "\nQuestion:",
        "\nWe need",
        "\nIt looks like",
        "\nIt appears",
        " ... ...",
        "......",
    ):
        if bad_tail in answer:
            answer = answer.split(bad_tail, 1)[0].strip()

    if "\n\n" in answer:
        answer = answer.split("\n\n", 1)[0].strip()

    return answer


def call_confidential_agent(query: str) -> dict[str, Any] | None:
    if not CONFIDENTIAL_AGENT_URL:
        return None

    message = {
        "messageType": "request",
        "format": "text",
        "subformat": "english",
        "content": query,
    }
    req = urllib.request.Request(
        CONFIDENTIAL_AGENT_URL,
        data=json.dumps(message).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": AGENT_NAME,
        "model": MODEL_NAME,
        "knowledge_chunks": len(load_knowledge_base()),
        "confidential_agent_configured": bool(CONFIDENTIAL_AGENT_URL),
    }


@app.post("/nlip")
def handle_nlip(message: NLIPMessage) -> dict[str, Any]:
    query = extract_query(message)
    contexts = retrieve(query)

    try:
        answer = ask_llm(query, contexts)
    except Exception as error:
        answer = None
        llm_error = str(error)
    else:
        llm_error = None

    if not answer:
        if contexts:
            answer = "I found potentially relevant NLIP source material, but no LLM answer was generated."
        else:
            answer = "The current knowledge base does not contain enough information."

    extra: dict[str, Any] = {}
    query_lower = query.lower()
    if "confidential" in query_lower or "project context" in query_lower:
        try:
            confidential_response = call_confidential_agent(query)
        except Exception as error:
            extra["confidential_agent_error"] = str(error)
        else:
            if confidential_response is not None:
                extra["confidential_agent_response"] = confidential_response

    if llm_error:
        extra["llm_error"] = llm_error

    return nlip_response(
        {
            "agent": AGENT_NAME,
            "answer": answer,
            "received_query": query,
            "model": MODEL_NAME,
            "sources": [
                {
                    "source": item.get("source"),
                    "url": item.get("url"),
                    "score": item.get("score"),
                }
                for item in contexts
            ],
            "extra": extra,
        },
        subformat="nlip-agent-response",
    )
