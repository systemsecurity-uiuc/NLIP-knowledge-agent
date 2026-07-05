# NLIP Knowledge Agent

Long-running NLIP knowledge agent for answering questions about NLIP.

The service accepts ECMA-430-shaped NLIP messages:

```json
{
  "messageType": "request",
  "format": "text",
  "subformat": "english",
  "content": "What is NLIP?"
}
```

It responds with:

```json
{
  "messageType": "response",
  "format": "json",
  "subformat": "nlip-agent-response",
  "content": {
    "agent": "nlip-knowledge-agent",
    "answer": "...",
    "sources": []
  }
}
```

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data
cp data/knowledge_base.sample.json data/knowledge_base.json
uvicorn app:app --host 0.0.0.0 --port 8080
```

## Build The Knowledge Base

```bash
pip install -r requirements.txt
python build_knowledge_base.py
```

The builder loads the NLIP website, ECMA TC56 page, ECMA-430 through ECMA-434, ECMA TR-113, and raw Markdown files from `nlip-project/security_guidelines`.

## Optional Environment Variables

- `JETSTREAM_CHAT_URL`: OpenAI-compatible Jetstream inference endpoint
- `JETSTREAM_API_KEY`: optional API key if required by the endpoint
- `NLIP_MODEL_NAME`: model name, for example `llama-4-scout`
- `KNOWLEDGE_BASE_PATH`: path to the retrieval knowledge base
- `CONFIDENTIAL_AGENT_URL`: Skupper-reachable AWS confidential agent URL

## Test

```bash
curl -s -X POST http://localhost:8080/nlip \
  -H 'Content-Type: application/json' \
  -d '{"messageType":"request","format":"text","subformat":"english","content":"What is NLIP?"}'
```
