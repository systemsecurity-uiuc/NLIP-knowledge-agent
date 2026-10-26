# NLIP Knowledge Agent

Long-running NLIP knowledge agent for answering questions about NLIP.

This version also includes a pluggable **NLIP Security Guard** for Track 3
security experiments. The guard inspects NLIP messages before the knowledge
agent processes them, blocks unsafe or malformed messages, and writes audit
records for both allowed and blocked traffic.

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
  "format": "structured",
  "subformat": "json",
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

For local security-demo testing on port 8088:

```bash
uvicorn app:app --host 127.0.0.1 --port 8088
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
- `NLIP_MODEL_NAME`: model name, for example `gemma-4-31b-it`
- `KNOWLEDGE_BASE_PATH`: path to the retrieval knowledge base
- `CONFIDENTIAL_AGENT_URL`: Skupper-reachable AWS confidential agent URL
- `RETRIEVAL_MIN_SCORE`: minimum retrieval score before the agent treats source context as strong enough for retrieval-augmented answering
- `SECURITY_POLICY_PATH`: optional JSON policy override for the NLIP Security Guard
- `SECURITY_AUDIT_LOG`: JSONL audit log path, default `security_audit.jsonl`
- `SECURITY_ADMIN_TOKEN`: administrator bearer token for `/security/audit`; audit access is disabled when unset. Keep it outside version control.
- `CORS_ALLOW_ORIGINS`: comma-separated browser origins; restrict this for production

`JETSTREAM_CHAT_URL` defaults to empty: export it explicitly to enable inference.
Knowledge responses label `generation_mode` as `model` or `unavailable`.
`answer_mode` describes retrieval selection, not model availability. Sources list
only excerpts supplied to inference.

## NLIP Security Guard

The security guard is packaged under `nlip_security_guard/` so it can later be
moved into or wrapped by the NLIP SDK. It currently provides:

- ECMA-430 required-field validation
- allowed `format` and `subformat` validation
- blocking of non-standard `sender` and `receiver` envelope fields
- prompt-injection phrase detection
- secret-exfiltration phrase detection
- unsafe-delegation phrase detection
- inbound and outbound security audit records

The default policy is built in. To customize it:

```bash
cp security_policy.example.json security_policy.local.json
export SECURITY_POLICY_PATH="$PWD/security_policy.local.json"
uvicorn app:app --host 127.0.0.1 --port 8088
```

Security status:

```bash
curl -s http://127.0.0.1:8088/security/status | python3 -m json.tool
```

Recent audit records:

```bash
curl -s -H "Authorization: Bearer $SECURITY_ADMIN_TOKEN" 'http://127.0.0.1:8088/security/audit?limit=10' | python3 -m json.tool
```

## Test

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/model-health
curl -s -X POST http://localhost:8080/nlip \
  -H 'Content-Type: application/json' \
  -d '{"messageType":"request","format":"text","subformat":"english","content":"What is NLIP?"}'
```

The agent answers with retrieved NLIP sources when they match strongly. If retrieval is weak, it falls back to a general LLM answer instead of behaving like a fixed FAQ.

Run the security guard unit tests:

```bash
python3 -m unittest discover -s tests
```

Install `requirements-dev.txt` for HTTP boundary tests. They use temporary audit
files and mocked inference. The SDK HTTP exchange test uses the real SDK client,
server, security managers, and ASGI HTTP transport with a deterministic fixture;
it does not establish live model or public network availability.

Run the end-to-end demo script while the app is running:

```bash
bash scripts/security_demo.sh
```

Expected demo behavior:

- a valid NLIP request is allowed and reaches the knowledge agent
- a prompt-injection request is blocked by `nlip-security-guard`
- an invalid top-level format such as `format: json` is blocked
- `/security/audit` shows the security decisions as JSONL-derived records

## Permanent Endpoint Plan

## Lab SDK Extension Integration

The optional adapter `nlip_security_guard.sdk_extension:KnowledgeSecurityExtension`
implements the lab framework's async `SecurityExtension.evaluate(event)` interface.
It maps server ingress/client egress to request checks and server egress/client
ingress to response checks. It returns explicit SDK ALLOW/BLOCK decisions.

Use the framework from https://github.com/systemsecurity-uiuc/NLIP-security-extensions
on `PYTHONPATH` together with this repository. Enable the extension using
`deploy/security_extensions.toml`. To reproduce integration tests:

```bash
pip install httpx
PYTHONPATH=/path/to/NLIP-security-extensions python -m unittest discover -s tests -v
```

The adapter has been tested with real SDK events and the configuration loader.
This does not yet mean the live FastAPI service is hosted by the SDK server.
Detection remains heuristic, and the regression cases are not a comprehensive
prompt-injection benchmark. Audit records omit message content to avoid recording
credentials. Restrict audit access before public deployment.

## Permanent Hosting

The current Jetstream deployment runs the FastAPI app as a `systemd` service
bound to `127.0.0.1:8091`. Tailscale Funnel publishes the persistent HTTPS route
`https://nlip-knowledge-jetstream.tail1f5426.ts.net/nlip`, which the GitHub
Pages client can call. See `deploy/permanent_endpoint_plan.md` for the topology
and verification steps. The Caddy and systemd files in `deploy/` are examples
for other hosts; they are not the current Funnel configuration.

Before installing the example systemd unit, create its referenced
`security_policy.local.json` and root-owned `/etc/nlip-knowledge-agent.env` (mode
0600). The environment file should set a strong `SECURITY_ADMIN_TOKEN` and
`CORS_ALLOW_ORIGINS=https://systemsecurity-uiuc.github.io`. Do not commit tokens.

The small transparent regression evaluation is `python -m scripts.evaluate_guard`.
Read `SECURITY_SCOPE.md` for its limits and remaining completion evidence.
