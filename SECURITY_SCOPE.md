# Security scope and completion evidence

## Intended contribution

A reusable communication-boundary guard for an NLIP knowledge application,
with an optional adapter for the lab SDK. The prototype covers message shape,
direct prompt injection, disclosure requests, unsafe-delegation phrases, and
selected outbound credential signatures. These are local policies, not a claim
of full ECMA-434 compliance.

## Threat model

An unauthenticated caller controls request content and submessages. A model or
retrieved document can produce unsafe response content. Protected assets include
model instructions, any credentials accidentally present in generated output,
and audit metadata. The attacker does not control the deployed policy, service
environment, host, or administrator audit token. The guard neither grants access
to confidential data nor implements per-user authorization.

Ingress is checked before retrieval/inference. Egress is checked before returning
the assembled response. In the standalone app these are direct calls; in the SDK
adapter they are extension checkpoints. The adapter currently returns decisions
without persisting the standalone application's audit log.

## Current evaluation

Run `python -m scripts.evaluate_guard` for a transparent, small regression suite.
It includes deliberate paraphrase bypasses, unsupported secret types, and a benign
discussion that causes a false positive. Its pass rate means passing the guard,
not causing actual model compromise. It cannot measure indirect prompt injection
or end-to-end attack success. The no-guard baseline permits all inputs by design.

Run tests with the framework on PYTHONPATH. The inspected framework revision is
`a93b66c29035f0bfabe4974cbf7dc8ebe1d392a9` from
https://github.com/systemsecurity-uiuc/NLIP-security-extensions.
The SDK HTTP test uses real client/server/manager pipelines over in-process ASGI
HTTP with a deterministic handler. It is not a live Jetstream inference test.

## Remaining evidence before completion

- Select and cite a research technique; justify its adaptation against a baseline.
- Evaluate representative published attacks and benign data with documented splits,
  sample counts, false positives, actual attack success, and latency.
- Test retrieved-document attacks: current input filtering does not inspect corpus
  excerpts, and phrase matching cannot establish a trusted instruction boundary.
- Deploy full corpus and tested guard to Jetstream; confirm real inference.
- Establish stable HTTPS, restrict CORS, configure the administrator audit token,
  and test browser access plus persistence across restart/SSH disconnect.
- Prepare reproducible submission materials and a recording using the live service.

## Known limits

Phrase matching is bypassable and can block educational discussion. Signature
matching misses many secret formats. Content limits do not bound total HTTP body,
model spending, or request frequency. Audit storage needs rotation and operational
monitoring. Public status/model-health endpoints remain available. Service health
does not prove model health. Course details in the separately linked Track 3 PDF
are unconfirmed because that document has not been supplied.
