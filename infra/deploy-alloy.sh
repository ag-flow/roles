#!/bin/bash
###############################################################################
# Déploiement de l'agent Alloy (collecteur logs) sur un LXC du homelab.
#
# A executer depuis le poste local (Windows/Linux) à la racine du repo
# agflow.roles. Utilise le host Proxmox (alias SSH `pve` par défaut) comme
# bastion : pct push pour copier les fichiers, pct exec pour le up.
#
# Usage :
#   ./infra/deploy-alloy.sh <CTID>
#
# Variables :
#   PVE_HOST   - alias SSH du host Proxmox (défaut : pve)
#   LOKI_URL   - endpoint Loki central (défaut : http://192.168.10.110:3100/loki/api/v1/push)
#   HOSTNAME   - identifiant du LXC label `host` (défaut : lxc<CTID>)
#
# Le script choisit automatiquement la bonne variante de config :
#   - Si Docker est installé dans le LXC -> mode container (config.alloy)
#   - Sinon -> mode binaire systemd via 02-install-alloy.sh
###############################################################################
set -euo pipefail

CTID="${1:-}"
PVE_HOST="${PVE_HOST:-pve}"
LOKI_URL="${LOKI_URL:-http://192.168.10.110:3100/loki/api/v1/push}"

if [ -z "${CTID}" ]; then
    echo "Usage: $0 <CTID>" >&2
    exit 1
fi

HOSTNAME_LABEL="${HOSTNAME:-lxc${CTID}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALLOY_AGENT_DIR="${SCRIPT_DIR}/alloy-agent"

if [ ! -d "${ALLOY_AGENT_DIR}" ]; then
    echo "ERREUR : ${ALLOY_AGENT_DIR} introuvable." >&2
    exit 1
fi

echo "==========================================="
echo "  Deploiement Alloy collecteur"
echo "==========================================="
echo "  CTID        : ${CTID}"
echo "  PVE_HOST    : ${PVE_HOST}"
echo "  HOSTNAME    : ${HOSTNAME_LABEL}"
echo "  LOKI_URL    : ${LOKI_URL}"
echo ""

# ── Détection Docker dans le LXC ─────────────────────────────────────────────
echo "[1/4] Détection Docker dans le LXC ${CTID}..."
HAS_DOCKER=0
if ssh "${PVE_HOST}" "pct exec ${CTID} -- bash -c 'command -v docker &>/dev/null && [ -S /var/run/docker.sock ]'" 2>/dev/null; then
    HAS_DOCKER=1
    echo "  -> Docker présent (mode container)"
else
    echo "  -> Docker absent (mode binaire systemd)"
fi

# ── Push des fichiers ────────────────────────────────────────────────────────
echo "[2/4] Push des fichiers Alloy vers le LXC..."
ssh "${PVE_HOST}" "pct exec ${CTID} -- mkdir -p /opt/alloy"
for f in docker-compose.yml config.alloy config-journald-only.alloy; do
    ssh "${PVE_HOST}" "pct push ${CTID} ${ALLOY_AGENT_DIR}/${f} /opt/alloy/${f}" 2>/dev/null \
        || ssh "${PVE_HOST}" "cat > /tmp/alloy-${CTID}-${f} && pct push ${CTID} /tmp/alloy-${CTID}-${f} /opt/alloy/${f}" < "${ALLOY_AGENT_DIR}/${f}"
done
# .env basé sur le template, on injecte LOKI_URL/HOSTNAME directement
ssh "${PVE_HOST}" "pct exec ${CTID} -- bash -c 'cat > /opt/alloy/.env << EOF
LOKI_URL=${LOKI_URL}
HOSTNAME=${HOSTNAME_LABEL}
EOF'"
echo "  -> /opt/alloy/{docker-compose.yml, config.alloy, config-journald-only.alloy, .env} en place"

# ── Démarrage ────────────────────────────────────────────────────────────────
if [ "${HAS_DOCKER}" -eq 1 ]; then
    echo "[3/4] docker compose up -d..."
    ssh "${PVE_HOST}" "pct exec ${CTID} -- bash -c 'cd /opt/alloy && docker compose pull >/dev/null 2>&1 && docker compose up -d'" | tail -5
    echo "  -> Container agflow-alloy-agent up"
else
    echo "[3/4] Mode systemd binaire — utilise 02-install-alloy.sh"
    ssh "${PVE_HOST}" "pct push ${CTID} ${SCRIPT_DIR}/02-install-alloy.sh /root/02-install-alloy.sh"
    ssh "${PVE_HOST}" "pct exec ${CTID} -- chmod +x /root/02-install-alloy.sh"
    ssh "${PVE_HOST}" "pct exec ${CTID} -- env LOKI_URL=${LOKI_URL} HOSTNAME=${HOSTNAME_LABEL} ALLOY_SRC_DIR=/opt/alloy /root/02-install-alloy.sh" | tail -10
fi

# ── Smoke ────────────────────────────────────────────────────────────────────
echo "[4/4] Smoke check..."
sleep 3
LXC_IP=$(ssh "${PVE_HOST}" "pct exec ${CTID} -- ip -4 addr show eth0 2>/dev/null | grep inet | awk '{print \$2}' | cut -d/ -f1 | head -1")
READY=$(ssh "${PVE_HOST}" "pct exec ${CTID} -- curl -fsS http://localhost:12345/-/ready 2>&1" || echo "FAILED")
if echo "${READY}" | grep -qi "ready"; then
    echo "  -> Alloy ready (http://${LXC_IP}:12345/-/ready)"
else
    echo "  [!] Alloy pas ready : ${READY}"
    if [ "${HAS_DOCKER}" -eq 1 ]; then
        ssh "${PVE_HOST}" "pct exec ${CTID} -- docker logs agflow-alloy-agent --tail 20 2>&1" | head -25
    else
        ssh "${PVE_HOST}" "pct exec ${CTID} -- journalctl -u alloy.service --no-pager -n 20 2>&1" | head -25
    fi
fi

echo ""
echo "==========================================="
echo "  Alloy déployé sur LXC ${CTID} (${LXC_IP})"
echo "==========================================="
echo ""
echo "  Vérifier dans Grafana :"
echo "    https://log.yoops.org → Explore (datasource Loki)"
echo '    {module="roles", host="'"${HOSTNAME_LABEL}"'"}'
echo ""
