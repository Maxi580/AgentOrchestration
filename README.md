# llm-d Inference Stack

Distributed LLM inference on OpenShift using [llm-d](https://llm-d.ai), deployed via Helm and helmfile.

## Repository Structure

```
├── helmfile.yaml                        # Orchestrates all three Helm charts
├── infra/
│   └── values.yaml                      # Gateway configuration (Istio, shared)
├── gaie/
│   └── values.yaml                      # EPP + InferencePool (smart routing)
├── models/
│   └── llama-3-8b/
│       ├── values.yaml                  # Model-specific vLLM config
│       └── httproute.yaml               # Routes requests to this model's pool
└── README.md
```

## Architecture

```
Client
  │
  ▼
Istio Gateway (infra)          ← single entry point, port 80
  │
  ▼
HTTPRoute                      ← matches model name, picks the right pool
  │
  ▼
InferencePool + EPP (gaie)     ← scores pods by cache/queue/GPU, picks best one
  │
  ▼
vLLM decode pods (ms)          ← serves the model
```

## Prerequisites

### Cluster requirements

- OpenShift 4.17+ with GPU worker nodes
- NVIDIA GPU Operator and Node Feature Discovery installed
- Service Mesh 3 (Istio) or a Gateway API implementation available
- Gateway API CRDs and InferencePool CRDs present on the cluster
- Cluster-admin or namespace-editor permissions (depending on what's already installed)

### Client tools

Install these on your local machine:

| Tool | Purpose | Install |
|------|---------|---------|
| `oc` | OpenShift CLI | Comes with OpenShift |
| `helm` | Helm 3.10+ | https://helm.sh/docs/intro/install/ |
| `helmfile` | Orchestrates multiple Helm releases | https://github.com/helmfile/helmfile |
| `yq` | YAML processor (used by some scripts) | https://github.com/mikefarah/yq |

## Setup (one-time)

### 1. Create the namespace

```powershell
oc new-project llm-d
```

### 2. Create the HuggingFace token secret

Get a token from https://huggingface.co/settings/tokens, then:

```powershell
oc create secret generic llm-d-hf-token `
  --from-literal="HF_TOKEN=<your-token>" `
  --namespace llm-d
```

> **Note:** For gated models like Llama 3, your HuggingFace account must have accepted the model's license agreement on the model page first.

### 3. Add the Helm repositories

```powershell
helm repo add llm-d-infra https://llm-d-incubation.github.io/llm-d-infra/
helm repo add llm-d-modelservice https://llm-d-incubation.github.io/llm-d-modelservice/
helm repo update
```

### 4. Verify cluster readiness

```powershell
# Confirm GPU nodes are available
oc get nodes -l node-role.kubernetes.io/gpu-worker

# Confirm Gateway API CRDs exist
oc get crd gateways.gateway.networking.k8s.io
oc get crd inferencepools.inference.networking.k8s.io

# Confirm no CRD conflicts
oc get crd | Select-String -Pattern "istio"
# (Istio CRDs should be present from Service Mesh — that's expected and fine)
```

## Deploy

### Deploy the full stack

```powershell
helmfile apply -n llm-d
```

This installs in order: gateway → EPP/InferencePool → vLLM model pods.

### Apply the HTTPRoute

```powershell
oc apply -f models/llama-3-8b/httproute.yaml -n llm-d
```

### Verify the deployment

```powershell
# Check all pods are running
oc get pods -n llm-d

# Check Helm releases
helm list -n llm-d

# Check the gateway, InferencePool, and HTTPRoute
oc get gateway -n llm-d
oc get inferencepool -n llm-d
oc get httproute -n llm-d
```

## Test

### Port-forward to the gateway

```powershell
oc port-forward -n llm-d svc/infra-inference-gateway-istio 8080:80
```

### Send a test request

```powershell
curl -X POST http://localhost:8080/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "messages": [{"role": "user", "content": "Hello, how are you?"}],
    "max_tokens": 50
  }'
```

## Adding a new model

1. Create a new directory under `models/` with a `values.yaml` and `httproute.yaml`
2. Add a new `gaie-*` release and `ms-*` release to `helmfile.yaml` (the `infra` release is shared)
3. Run `helmfile apply -n llm-d`
4. Apply the new HTTPRoute: `oc apply -f models/<model>/httproute.yaml -n llm-d`

## Teardown

```powershell
# Remove the HTTPRoute
oc delete -f models/llama-3-8b/httproute.yaml -n llm-d

# Remove all Helm releases
helmfile destroy -n llm-d
```

## Useful commands

```powershell
# Follow vLLM pod logs
oc logs -f -l app=vllm-llama-3-8b -n llm-d

# Check EPP scheduling decisions
oc logs -f -l app.kubernetes.io/name=llm-d-inference-scheduler -n llm-d

# Check which models are available through the gateway
curl http://localhost:8080/v1/models

# Check GPU utilization on a node
oc adm top node <gpu-worker-node>
```

## References

- [llm-d documentation](https://llm-d.ai/docs/guide)
- [llm-d OpenShift guide](https://github.com/llm-d/llm-d/blob/main/docs/infra-providers/openshift/README.md)
- [Inference scheduling guide](https://llm-d.ai/docs/guide/Installation/inference-scheduling)
- [Gateway API Inference Extension](https://gateway-api-inference-extension.sigs.k8s.io/)