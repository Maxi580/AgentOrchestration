# llm-d on OpenShift — Setup Guide & Architecture

This documents the full setup of [llm-d](https://llm-d.ai) for distributed LLM inference on Red Hat OpenShift, deployed via Helm. Everything here was validated on a live cluster.

## What is llm-d?

llm-d is a Kubernetes-native distributed inference stack that sits on top of vLLM. Where plain vLLM gives you a single model server, llm-d adds intelligent request routing, KV cache-aware scheduling, and the ability to split inference into separate prefill and decode phases.

It was created by Red Hat, Google, IBM, and NVIDIA, and is built on three open-source components: vLLM (model serving), Kubernetes Gateway API (traffic management), and Kubernetes itself (orchestration).

### Why not just run vLLM directly?

With a single vLLM pod, there's no difference. The value shows up when you scale:

- **Multiple replicas**: llm-d's EPP (Endpoint Picker Proxy) routes each request to the pod with the best KV cache hit, shortest queue, or most free GPU memory — instead of dumb round-robin.
- **Disaggregated serving**: Separate pods for prompt processing (prefill) and token generation (decode), each optimized for their workload.
- **Multi-model serving**: Multiple models behind a single gateway endpoint, routed by the `model` field in the request body.

In benchmarks, this delivers up to 3x improvement in time-to-first-token and doubles throughput under SLO constraints compared to a plain Kubernetes service.

## Architecture

```
Client request
    │
    ▼
┌─────────────────────────────────┐
│  Istio Gateway (infra)          │  ← Single entry point for all requests
│  Port 80                        │     Deployed once, shared across models
└───────────────┬─────────────────┘
                │
    ┌───────────▼────────────┐
    │  HTTPRoute             │  ← "Which model?" — routes based on model name
    │  (one per model)       │     Connects gateway to the right InferencePool
    └───────────┬────────────┘
                │
    ┌───────────▼────────────┐
    │  InferencePool + EPP   │  ← "Which pod?" — scores pods by cache/queue/GPU
    │  (gaie, one per model) │     Picks the optimal vLLM pod for each request
    └───────────┬────────────┘
                │
    ┌───────────▼────────────┐
    │  vLLM decode pods      │  ← Runs the model, generates tokens
    │  (ms, one per model)   │     Can scale to multiple replicas
    └────────────────────────┘
```

## What each component does

| Component | Helm chart | What it creates | Purpose |
|-----------|-----------|-----------------|---------|
| **infra** | `llm-d-infra` | Istio Gateway pod + service | Front door — receives all incoming requests |
| **gaie** | `inferencepool` (upstream) | EPP pod + InferencePool resource | Brain — monitors vLLM pods and picks the best one per request |
| **ms** (modelservice) | `llm-d-modelservice` | vLLM Deployment + Service | Worker — loads and serves the actual model |
| **HTTPRoute** | Manual YAML | HTTPRoute resource | Glue — connects the gateway to the correct InferencePool |

### How the EPP makes routing decisions

The EPP runs a plugin pipeline for every incoming request:

1. **queue-scorer** — pods with shorter request queues score higher
2. **prefix-scorer** — pods that already cached similar prompt prefixes score higher
3. **least-kv-cache-scorer** — pods with more free GPU cache memory score higher
4. **max-score-picker** — picks the pod with the highest combined score

With a single replica, routing is trivial. With multiple replicas, this is where the performance gains come from.

### How the label chain works

The entire system is connected by Kubernetes labels:

```
modelservice values.yaml         GAIE install
─────────────────────────        ─────────────────────────
modelArtifacts:                  --set inferencePool.modelServers
  labels:                             .matchLabels.app=vllm-llama-3-8b
    app: vllm-llama-3-8b
         │                                    │
         └──── vLLM pods get this label ──────┘
                      │
              InferencePool watches for
              pods with this label
```

If these labels don't match, the EPP sees zero endpoints and returns "ServiceUnavailable - failed to find candidate pods."

## Cluster requirements

Validated on:
- **OpenShift**: 4.21 (also tested by llm-d on 4.17, 4.19, 4.20)
- **Kubernetes**: 1.34
- **Service Mesh**: Red Hat OpenShift Service Mesh 3 (v3.2.0)
- **GPU Operator**: NVIDIA GPU Operator with Node Feature Discovery
- **Gateway class**: `data-science-gateway-class` (from Service Mesh 3)
- **Region**: AWS eu-west-1

### Cluster layout

```
3x control-plane nodes    — tainted, no workloads
3x gpu-worker nodes       — tainted with nvidia.com/gpu, run vLLM pods
1x infra node             — runs gateway, EPP, Langflow, etc.
```

### CRDs that must exist before deployment

These were already present from Service Mesh 3 and RHOAI:
- `gateways.gateway.networking.k8s.io`
- `httproutes.gateway.networking.k8s.io`
- `inferencepools.inference.networking.k8s.io`

Check with: `oc get crd | Select-String -Pattern "gateway|inferencepool"`

### Important: Service Mesh compatibility

OpenShift Service Mesh 3 installs Istio CRDs cluster-wide. llm-d docs warn about CRD conflicts, but **this is fine** if you use the existing Istio as your gateway provider instead of installing a second one. Set `gateway.provider: istio` and `gateway.gatewayClassName: data-science-gateway-class` in the infra values.

## Repository structure

```
├── infra/
│   └── values.yaml                  # Gateway config (Istio, shared, deploy once)
├── gaie/
│   └── values.yaml                  # EPP + InferencePool config (one per model)
├── models/
│   └── llama-3-8b/
│       ├── values.yaml              # Model-specific vLLM config
│       └── httproute.yaml           # Routes requests to this model's pool
├── helmfile.yaml                    # Orchestrates all three charts (requires helmfile CLI)
└── README.md
```

## Setup (one-time)

### 1. Install Helm on your local machine

```powershell
winget install Helm.Helm
# Close and reopen PowerShell, then verify:
helm version
```

### 2. Add the Helm repositories

```powershell
helm repo add llm-d-infra https://llm-d-incubation.github.io/llm-d-infra/
helm repo add llm-d-modelservice https://llm-d-incubation.github.io/llm-d-modelservice/
helm repo update
```

### 3. Create the HuggingFace token secret

Create a Read token at https://huggingface.co/settings/tokens, then:

```powershell
oc create secret generic llm-d-hf-token `
  --from-literal="HF_TOKEN=hf_yourtoken" `
  --namespace maxi-agent-orchestration
```

**Important for gated models**: For models like Llama 3, you must visit the model page on HuggingFace and accept the license agreement. Some models approve instantly, others require review.

## Deploy

Run these four commands in order from the repo directory:

```powershell
# Step 1: Gateway (front door)
helm install infra llm-d-infra/llm-d-infra `
  -f infra/values.yaml `
  -n maxi-agent-orchestration

# Step 2: EPP + InferencePool (smart routing brain)
helm install gaie-llama `
  --set inferencePool.modelServers.matchLabels.app=vllm-llama-3-8b `
  --set provider.name=istio `
  --version v1.1.0 `
  -n maxi-agent-orchestration `
  oci://registry.k8s.io/gateway-api-inference-extension/charts/inferencepool

# Step 3: vLLM model pods
helm install ms-llama llm-d-modelservice/llm-d-modelservice `
  -f models/llama-3-8b/values.yaml `
  -n maxi-agent-orchestration

# Step 4: Connect gateway to pool
oc apply -f models/llama-3-8b/httproute.yaml -n maxi-agent-orchestration
```

### Verify

```powershell
# All pods should be Running
oc get pods -n maxi-agent-orchestration

# Gateway should show PROGRAMMED: True
oc get gateway -n maxi-agent-orchestration

# InferencePool should exist
oc get inferencepool -n maxi-agent-orchestration

# HTTPRoute should show Accepted: True
oc describe httproute llama-3-8b-route -n maxi-agent-orchestration
```

Expected pod output:
```
NAME                                                              READY   STATUS
infra-inference-gateway-data-science-gateway-class-...            1/1     Running
gaie-llama-epp-...                                                1/1     Running
ms-llama-llm-d-modelservice-decode-...                            1/1     Running
```

## Test

### Port-forward the gateway

```powershell
oc port-forward -n maxi-agent-orchestration svc/infra-inference-gateway-data-science-gateway-class 8080:80
```

### Send a request (in a second terminal)

```powershell
Invoke-WebRequest -Uri "http://localhost:8080/v1/chat/completions" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"model": "Qwen/Qwen3-0.6B", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 50}'
```

### How to confirm the request went through llm-d

Check the response headers for `x-went-into-resp-headers: true` — this is injected by the EPP. A direct vLLM call wouldn't have it.

Check EPP logs for routing decisions:
```powershell
oc logs -l app.kubernetes.io/name=llm-d-inference-scheduler -n maxi-agent-orchestration --tail=10
```

## Adding a second model

1. Create `models/tinyllama/values.yaml` with different `modelArtifacts.name`, `uri`, and labels (e.g., `app: vllm-tinyllama`)
2. Create `models/tinyllama/httproute.yaml` pointing to the new InferencePool
3. Deploy a new GAIE release with matching labels:
```powershell
helm install gaie-tinyllama `
  --set inferencePool.modelServers.matchLabels.app=vllm-tinyllama `
  --set provider.name=istio `
  --version v1.1.0 `
  -n maxi-agent-orchestration `
  oci://registry.k8s.io/gateway-api-inference-extension/charts/inferencepool
```
4. Deploy the model: `helm install ms-tinyllama llm-d-modelservice/llm-d-modelservice -f models/tinyllama/values.yaml -n maxi-agent-orchestration`
5. Apply the HTTPRoute: `oc apply -f models/tinyllama/httproute.yaml -n maxi-agent-orchestration`

The gateway is shared — both models are accessible from the same endpoint. Clients select the model via the `model` field in the request body.

## Scaling up

### More replicas (immediate benefit)

Change `decode.replicas` in the model values and upgrade:
```powershell
helm upgrade ms-llama llm-d-modelservice/llm-d-modelservice `
  -f models/llama-3-8b/values.yaml `
  -n maxi-agent-orchestration
```

With 2+ replicas, the EPP starts making meaningful routing decisions — cache-aware, load-aware, GPU-aware.

### Disaggregated serving (advanced)

Set `prefill.replicas: 1` to split inference into separate prefill and decode pods. Requires updating the GAIE config with P/D-aware scheduling profiles. See the [llm-d P/D guide](https://llm-d.ai/docs/guide/Installation/pd-disaggregation).

## Gotchas we discovered

### Gateway class mismatch
The default `gatewayClassName` is `istio`, but OpenShift Service Mesh 3 registers `data-science-gateway-class`. Set `gateway.gatewayClassName: "data-science-gateway-class"` in infra values.

### GPU node taints
GPU worker nodes are tainted with `nvidia.com/gpu`. vLLM pods need an explicit toleration:
```yaml
decode:
  tolerations:
    - key: nvidia.com/gpu
      operator: Exists
      effect: NoSchedule
```

### Infra node capacity
The gateway and EPP pods are lightweight but need CPU. If the infra node is full, they stay Pending. They don't need GPUs — if stuck, adding the GPU toleration lets them land on GPU workers too.

### OpenShift permissions
Containers run as non-root. vLLM needs writable directories for caches:
```yaml
env:
  - name: HOME
    value: /tmp
  - name: VLLM_CACHE_ROOT
    value: /tmp/vllm
```
Don't set `HF_HOME` manually — the modelservice chart injects it automatically from `modelArtifacts` config. Duplicating it causes deployment failures.

### Gated models
Some HuggingFace models (like Llama 3) require license acceptance. The pod will crash with `403 Client Error` if access isn't granted. Check the model page on HuggingFace. Some approvals are instant, others require review.

### Port-forward dies on pod restart
Every time a pod restarts or you redeploy, the `oc port-forward` session breaks. You need to restart it manually.

### PowerShell curl alias
PowerShell aliases `curl` to `Invoke-WebRequest`. Use `curl.exe` for real curl, or use `Invoke-WebRequest` with PowerShell syntax.

### HTTPRoute names must match actual resources
The `parentRefs.name` and `backendRefs.name` in the HTTPRoute must match the real resource names generated by the Helm charts. Always check with `oc get gateway` and `oc get inferencepool` after deploying infra and gaie.

## Teardown

```powershell
# Remove in reverse order
oc delete -f models/llama-3-8b/httproute.yaml -n maxi-agent-orchestration
helm uninstall ms-llama -n maxi-agent-orchestration
helm uninstall gaie-llama -n maxi-agent-orchestration
helm uninstall infra -n maxi-agent-orchestration
```

## Useful commands

```powershell
# Check all pods
oc get pods -n maxi-agent-orchestration

# Check what labels a pod has (for debugging label mismatches)
oc get pod <pod-name> -n maxi-agent-orchestration --show-labels

# Follow vLLM logs
oc logs -f -l app=vllm-llama-3-8b -n maxi-agent-orchestration

# Follow EPP scheduling logs
oc logs -f -l app.kubernetes.io/name=llm-d-inference-scheduler -n maxi-agent-orchestration

# Check available models through the gateway
curl.exe http://localhost:8080/v1/models

# Check Helm releases
helm list -n maxi-agent-orchestration

# See what a chart expects (before writing values files)
helm show values llm-d-infra/llm-d-infra
helm show values llm-d-modelservice/llm-d-modelservice
helm show values --version v1.1.0 oci://registry.k8s.io/gateway-api-inference-extension/charts/inferencepool
```

## References

- [llm-d documentation](https://llm-d.ai/docs/guide)
- [llm-d OpenShift guide](https://github.com/llm-d/llm-d/blob/main/docs/infra-providers/openshift/README.md)
- [Inference scheduling guide](https://llm-d.ai/docs/guide/Installation/inference-scheduling)
- [Gateway API Inference Extension](https://gateway-api-inference-extension.sigs.k8s.io/)
- [llm-d GitHub](https://github.com/llm-d/llm-d)
- [Multi-model on OpenShift (Red Hat)](https://developers.redhat.com/articles/2026/03/24/run-model-service-multiple-llms-openshift)