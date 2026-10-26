# Permanent Endpoint Plan

The local/demo setup can use temporary HTTPS tunnels, but a long-running NLIP
knowledge agent should use a stable HTTPS endpoint.

## Recommended Path

1. Run the knowledge agent as a `systemd` service on the Jetstream VM.
2. Bind the FastAPI app to localhost only, for example `127.0.0.1:8088`.
3. Put Caddy or another HTTPS reverse proxy in front of the service.
4. Point a stable DNS name, such as an NLIP project subdomain, to the Jetstream
   VM public IP.
5. Configure the universal client to use:

```text
https://<stable-domain>/nlip
```

## Why This Path

- The Python agent does not need to handle TLS directly.
- Caddy can manage HTTPS certificates automatically once DNS points correctly.
- The app stays private on localhost, while only the HTTPS proxy is public.
- The endpoint remains stable across terminal sessions and browser refreshes.

## Example Files

- `deploy/nlip-knowledge-agent.service.example`
- `deploy/Caddyfile.example`

## Open Decision

The remaining deployment choice is the domain name. Once the NLIP project decides
whether to use a subdomain under `nlip-project.org` or another stable DNS name,
the example Caddyfile can be updated and deployed.
