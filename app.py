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
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.2"))
SOURCE_KEYWORD_BOOSTS = {
    "what is nlip": "ECMA-430 Natural Language Interaction Protocol",
    "natural language interaction protocol": "ECMA-430 Natural Language Interaction Protocol",
    "ecma-430": "ECMA-430 Natural Language Interaction Protocol",
    "ecma 430": "ECMA-430 Natural Language Interaction Protocol",
    "http": "ECMA-431 NLIP over HTTP/HTTPS",
    "https": "ECMA-431 NLIP over HTTP/HTTPS",
    "websocket": "ECMA-432 NLIP over WebSocket",
    "amqp": "ECMA-433 NLIP over AMQP",
    "ecma-434": "ECMA-434 NLIP Security Profiles",
    "ecma 434": "ECMA-434 NLIP Security Profiles",
    "security": "ECMA-434 NLIP Security Profiles",
    "tr-113": "ECMA TR-113 NLIP Technical Report",
    "technical report": "ECMA TR-113 NLIP Technical Report",
}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "the", "to", "what", "with",
}


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
        "format": "structured",
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
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9-]+", text.lower())
        if token not in STOPWORDS and len(token) > 1
    }


def source_boost(query: str, source: str) -> float:
    query_lower = query.lower()
    source_lower = source.lower()
    for keyword, preferred_source in SOURCE_KEYWORD_BOOSTS.items():
        if keyword in query_lower and preferred_source.lower() in source_lower:
            return 0.35
    return 0.0


def retrieve(query: str, limit: int = 4) -> list[dict[str, Any]]:
    query_terms = tokenize(query)
    if not query_terms:
        return []

    scored = []
    for item in load_knowledge_base():
        text = item.get("text", "")
        source = item.get("source", "")
        terms = tokenize(text)
        # Lightweight retrieval: term overlap plus source-name boosts for common NLIP standards.
        score = len(query_terms & terms) / max(1, len(query_terms))
        score += source_boost(query, source)
        if score:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, item in scored[:limit]:
        result = dict(item)
        result["score"] = score
        results.append(result)
    return results


def retrieval_mode(contexts: list[dict[str, Any]]) -> str:
    if contexts and contexts[0].get("score", 0) >= RETRIEVAL_MIN_SCORE:
        return "retrieval_augmented"
    return "general_llm"


def build_prompt(query: str, contexts: list[dict[str, Any]]) -> str:
    if contexts:
        context_text = "\n\n".join(
            f"Source: {item.get('source', 'unknown')}\n{item.get('text', '')}"
            for item in contexts
        )
        return (
            "You are an NLIP knowledge assistant. NLIP means Natural Language "
            "Interaction Protocol. Answer the user's question clearly and concisely. "
            "Prefer a short direct answer followed by one or two important details. "
            "Use the provided source excerpts when they are relevant. If the excerpts "
            "are only partially relevant, say what you can from them and avoid making "
            "unsupported claims. Mention source names briefly when useful. Do not expose "
            "chain-of-thought or implementation notes.\n\n"
            f"Source excerpts:\n{context_text}\n\nQuestion: {query}\n\nAnswer:"
        )

    return (
        "You are an NLIP knowledge assistant. NLIP means Natural Language "
        "Interaction Protocol. Answer the user's question clearly and concisely. "
        "Prefer a short direct answer followed by one or two important details. "
        "If the question is outside the loaded NLIP material, answer from general "
        "knowledge and say that no local source excerpt was used. Do not expose "
        "chain-of-thought or implementation notes.\n\n"
        f"Question: {query}\n\nAnswer:"
    )


def clean_llm_answer(answer: str) -> str:
    answer = answer.strip()
    # Jetstream-hosted models sometimes echo prompt scaffolding; remove common demo noise.
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


def ask_llm(query: str, contexts: list[dict[str, Any]]) -> str | None:
    if not JETSTREAM_CHAT_URL:
        return None

    prompt = build_prompt(query, contexts)
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
            "stop": ["\nThe answer", "\nThe question", "\nWe need", "assistantfinal"],
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

    return clean_llm_answer(answer)


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


@app.get("/model-health")
def model_health() -> dict[str, Any]:
    if not JETSTREAM_CHAT_URL:
        return {
            "status": "not_configured",
            "agent": AGENT_NAME,
            "model": MODEL_NAME,
            "message": "JETSTREAM_CHAT_URL is not set.",
        }
    try:
        answer = ask_llm("Reply with only: model reachable", [])
    except Exception as error:
        return {
            "status": "error",
            "agent": AGENT_NAME,
            "model": MODEL_NAME,
            "message": str(error),
        }
    return {
        "status": "ok" if answer else "empty_response",
        "agent": AGENT_NAME,
        "model": MODEL_NAME,
        "sample": answer,
    }


@app.post("/nlip")
def handle_nlip(message: NLIPMessage) -> dict[str, Any]:
    query = extract_query(message)
    contexts = retrieve(query)
    mode = retrieval_mode(contexts)
    # If retrieval confidence is weak, still answer through the LLM instead of acting like a fixed FAQ.
    llm_contexts = contexts if mode == "retrieval_augmented" else []

    try:
        answer = ask_llm(query, llm_contexts)
    except Exception as error:
        answer = None
        llm_error = str(error)
    else:
        llm_error = None

    if not answer:
        if contexts:
            answer = "I found potentially relevant NLIP source material, but the LLM did not generate an answer."
        else:
            answer = "I could not generate an answer because the LLM is unavailable and no local source matched strongly."

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
            "answer_mode": mode,
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
        subformat="json",
    )
