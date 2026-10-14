#!/usr/bin/env bash
# Crée un cluster kind qui ressemble au cluster du cours, pour valider la charte Helm sans toucher au vrai cluster.
#
#   k8s/outils/kind-creer.sh [nom]          (nom par défaut : cinetint)
#   k8s/outils/kind-creer.sh [nom] supprimer
#
# Ce que le script installe, et pourquoi
#   * 1 control-plane + 2 workers : les pods se répartissent sur plusieurs nœuds comme sur RKE2.
#   * réseau des pods 10.42.0.0/16 et des services 10.43.0.0/16, comme RKE2.
#   * Calico à la place de kindnet : kindnet n'applique pas les NetworkPolicy (Défis 11 et 18).
#   * ingress-nginx (manifeste officiel pour kind) : l'Ingress du Défi 4, joignable sur http://localhost:8080 .
#   * metrics-server avec --kubelet-insecure-tls (kind seulement) : "kubectl top" et l'HPA du Défi 9.
# Prérequis : docker, kind, kubectl. Versions épinglées ci-dessous (vérifiées sur les dépôts officiels en octobre 2026).
set -euo pipefail

NOM="${1:-cinetint}"
ACTION="${2:-creer}"
PORT_HTTP="${PORT_HTTP:-8080}"
PORT_HTTPS="${PORT_HTTPS:-8443}"
CALICO="${CALICO:-v3.33.0}"
INGRESS_NGINX="${INGRESS_NGINX:-controller-v1.15.1}"
METRICS_SERVER="${METRICS_SERVER:-v0.9.0}"

if [ "$ACTION" = "supprimer" ]; then
    kind delete cluster --name "$NOM"
    exit 0
fi

config="$(mktemp)"
trap 'rm -f "$config"' EXIT
cat > "$config" <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: ${NOM}
networking:
  disableDefaultCNI: true
  podSubnet: "10.42.0.0/16"
  serviceSubnet: "10.43.0.0/16"
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - {containerPort: 80, hostPort: ${PORT_HTTP}, protocol: TCP}
      - {containerPort: 443, hostPort: ${PORT_HTTPS}, protocol: TCP}
  - role: worker
  - role: worker
EOF

echo "==> cluster kind ${NOM}"
kind create cluster --config "$config" --wait 0s

echo "==> Calico ${CALICO} (réseau des pods 10.42.0.0/16)"
curl -fsSL "https://raw.githubusercontent.com/projectcalico/calico/${CALICO}/manifests/calico.yaml" \
    | sed -e 's|# - name: CALICO_IPV4POOL_CIDR|- name: CALICO_IPV4POOL_CIDR|' \
          -e 's|#   value: "192.168.0.0/16"|  value: "10.42.0.0/16"|' \
    | kubectl apply -f - >/dev/null
kubectl -n kube-system rollout status daemonset/calico-node --timeout=300s
kubectl wait --for=condition=Ready nodes --all --timeout=300s

echo "==> ingress-nginx ${INGRESS_NGINX}"
curl -fsSL "https://raw.githubusercontent.com/kubernetes/ingress-nginx/${INGRESS_NGINX}/deploy/static/provider/kind/deploy.yaml" \
    | kubectl apply -f - >/dev/null
# le manifeste kind ne cible plus le nœud étiqueté ingress-ready : on le force (c'est le nœud qui publie les ports 80 et 443)
kubectl -n ingress-nginx patch deployment ingress-nginx-controller --type merge \
    -p '{"spec":{"template":{"spec":{"nodeSelector":{"ingress-ready":"true"}}}}}' >/dev/null
kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=300s
kubectl -n ingress-nginx wait --for=condition=complete job --all --timeout=300s >/dev/null 2>&1 || true

echo "==> metrics-server ${METRICS_SERVER}"
curl -fsSL "https://github.com/kubernetes-sigs/metrics-server/releases/download/${METRICS_SERVER}/components.yaml" \
    | sed -e 's|- --kubelet-use-node-status-port|- --kubelet-insecure-tls\n        - --kubelet-use-node-status-port|' \
    | kubectl apply -f - >/dev/null
kubectl -n kube-system rollout status deployment/metrics-server --timeout=300s

echo "==> cluster ${NOM} prêt : http://localhost:${PORT_HTTP} (Ingress), kubectl config use-context kind-${NOM}"
