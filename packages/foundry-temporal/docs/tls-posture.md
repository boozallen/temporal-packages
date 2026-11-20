# Temporal Client TLS Posture

`foundry-temporal` requires an explicit TLS posture for the Temporal client
transport. `create_temporal_client()` will **not** connect if `TEMPORAL_TLS_MODE`
is unset or invalid — it raises `ValueError`. This ensures every deployment makes
a conscious, auditable decision about how the connection to the Temporal frontend
is protected, rather than silently falling back to plaintext.

## Configuration

Set `TEMPORAL_TLS_MODE` (or pass `tls_mode` to `WorkerConfig`):

```bash
export TEMPORAL_TLS_MODE=platform
```

## Modes

### Platform mode

TLS is terminated by the deployment platform — a service mesh sidecar, ingress
controller, or cloud load balancer. The client connects without application-managed
TLS, trusting the platform to protect traffic in transit.

```bash
export TEMPORAL_TLS_MODE=platform
```

This is the standard configuration for EKS deployments with a service mesh that
enforces mTLS between pods. The application makes the trust boundary explicit.

### Off (alias for platform)

`off` behaves exactly like `platform`. The client connects without application-managed
TLS. Use it where no TLS exists at all, such as a local Temporal dev server, so the
configuration says so. The logged posture is `off`.

```bash
export TEMPORAL_TLS_MODE=off
```

### TLS mode (one-way)

The application manages transport TLS directly (server is verified). Provide a
custom CA and/or client certificate if required; otherwise system root CAs are used.

```bash
export TEMPORAL_TLS_MODE=tls
export TEMPORAL_TLS_CA=/etc/tls/ca.pem        # optional custom server CA
export TEMPORAL_TLS_CERT=/etc/tls/client.pem  # optional client certificate
export TEMPORAL_TLS_KEY=/etc/tls/client.key   # optional client private key
```

### mTLS mode (mutual)

The application presents a client certificate for mutual authentication. Both
`TEMPORAL_TLS_CERT` and `TEMPORAL_TLS_KEY` are **required**; the server CA is
optional (system roots are used when omitted).

```bash
export TEMPORAL_TLS_MODE=mtls
export TEMPORAL_TLS_CERT=/etc/tls/client.pem
export TEMPORAL_TLS_KEY=/etc/tls/client.key
export TEMPORAL_TLS_CA=/etc/tls/ca.pem        # optional custom server CA
```

Certificate provisioning (generation, rotation, renewal) is outside the scope of
this package. Use cert-manager, Kubernetes secrets, or your organization's PKI to
place the files at the configured paths.

## Startup behavior

| Condition | Result |
|-----------|--------|
| `TEMPORAL_TLS_MODE` unset | `create_temporal_client()` raises `ValueError` |
| `TEMPORAL_TLS_MODE` invalid value | `create_temporal_client()` raises `ValueError` |
| `TEMPORAL_TLS_MODE=platform` | Client connects with no application `tls` (mesh terminates TLS) |
| `TEMPORAL_TLS_MODE=off` | Same as `platform` (alias). The logged posture is `off` |
| `TEMPORAL_TLS_MODE=tls` | Client connects with transport TLS (custom cert/CA if provided, else system roots) |
| `TEMPORAL_TLS_MODE=mtls`, cert + key present | Client connects with mutual TLS |
| `TEMPORAL_TLS_MODE=mtls`, cert or key missing | `create_temporal_client()` raises `ValueError` |

The active posture is logged at connect time and included in
`WorkerConfig.to_dict()` (cert/key/CA paths are excluded from that output).

## Migration

Deployments that previously relied on the implicit no-TLS behavior must now set an
explicit posture. To reproduce the prior in-mesh behavior, add:

```bash
export TEMPORAL_TLS_MODE=platform
```

## STIG compliance

This satisfies STIG V-222596 (SRG-APP-000439) by ensuring transit protection is
explicitly declared, the client fails closed when the posture is not configured,
and the active TLS mode is recorded at startup.
