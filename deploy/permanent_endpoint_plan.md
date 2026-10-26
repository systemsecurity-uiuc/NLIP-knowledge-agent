# Persistent HTTPS endpoint

The knowledge agent runs on the Jetstream VM as
`nlip-knowledge-secure.service`, bound to `127.0.0.1:8091`. Tailscale Funnel
publishes that loopback service at:

```text
https://nlip-knowledge-jetstream.tail1f5426.ts.net/nlip
```

The browser frontend is hosted separately at
`https://systemsecurity-uiuc.github.io/NLIP-Agent-Universal-Client/`.
The app allows that GitHub Pages origin through `CORS_ALLOW_ORIGINS`.

## Why this route

The Jetstream host also runs Kubernetes, whose CNI rules intercept IPv4 ports
80 and 443 before host Caddy. Funnel publishes HTTPS without changing those
rules or binding the knowledge agent to a public interface. The `tailscaled`
daemon runs with `--tun=userspace-networking` to avoid changing host routes.
Funnel uses a stable `*.ts.net` hostname; `--bg` stores the serving configuration
so it resumes after a Tailscale daemon or machine restart. Tailscale Funnel is
currently a beta service, so external reachability still needs monitoring.

## Jetstream setup and checks

The service environment is in root-owned `/etc/nlip-knowledge-secure.env`. It
sets the model name and Jetstream chat URL, `CORS_ALLOW_ORIGINS`, and
`SECURITY_ADMIN_TOKEN`. Keep the token out of Git and terminal recordings.
The deployed knowledge base has 103 chunks.

```bash
systemctl is-active nlip-knowledge-secure.service tailscaled
sudo tailscale funnel status
sudo tailscale funnel --bg 8091
```

Only run the last command when Funnel needs to be configured again. The agent
must already respond at `http://127.0.0.1:8091/health` on the VM.
After a service or Tailscale restart, verify the public URL **from outside the
tailnet** rather than relying only on local `tailscale funnel status`:

```bash
curl -fsS https://nlip-knowledge-jetstream.tail1f5426.ts.net/health
```

The health route proves only that the service is reachable. Check
`/model-health`, a normal POST to `/nlip`, and a blocked attack before a demo.
The administrator audit endpoint requires its bearer token.

## Remaining operational cleanup

The secure systemd unit currently uses the separate
`/home/exouser/NLIP-knowledge-agent-staging` checkout at commit `988543d`.
After the security branch is published on `main`, point the unit at a stable
release checkout and retire old duplicate knowledge-agent processes only after
the replacement is verified. The builder and confidential-agent services are
separate and should not be stopped as part of this cleanup.
