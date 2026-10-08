#!/usr/bin/env bash
# Déploiement dev de roles — build local + docker compose + smoke test.
# Geste opérateur harmonisé avec le modèle devpod : sudo ./dev-deploy.sh [BRANCH]
#
# Drapeaux :
#   --bootstrap-deploy-key   génère/affiche la deploy key SSH de l'hôte, puis s'arrête
#   --no-hangup-guard        désactive le filet SIGHUP (intégration continue, débogage)
#   --force                  avec --bootstrap-deploy-key : régénère la clé existante
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERREUR : ce script doit être exécuté en root (sudo ./dev-deploy.sh)." >&2
    exit 1
fi

REPO_URL="git@github.com:ag-flow/roles.git"
DEPLOY_LOG="/var/log/roles-dev-deploy.log"
PURGE_STAMP="/var/lib/roles-dev-deploy/last-prune"
AUTO_PORTS="/var/lib/roles-dev-deploy/auto-ports"
DEPLOY_KEY="/root/.ssh/id_ed25519_roles_deploy"

BOOTSTRAP_KEY=0
HANGUP_GUARD=1
FORCE=0
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --bootstrap-deploy-key) BOOTSTRAP_KEY=1 ;;
        --no-hangup-guard)      HANGUP_GUARD=0 ;;
        --force)                FORCE=1 ;;
        *)                      ARGS+=("$arg") ;;
    esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

# --- 0) Survivre à la perte de la session ---
# Ce script arrête la stack qu'il pilote. Lancé depuis une session HÉBERGÉE par
# cette stack (terminal web, shell dans un conteneur du projet), il se coupe la
# branche : la session meurt, SIGHUP tue le script entre le `down` et le `up`,
# et la stack reste à moitié debout. Une connexion mobile qui tombe fait pareil.
# On ignore donc SIGHUP et on duplique toute la sortie dans un fichier, pour que
# le déploiement aille au bout ET reste diagnosticable sans le terminal.
if [[ "$HANGUP_GUARD" -eq 1 ]]; then
    trap '' HUP
    mkdir -p "$(dirname "$DEPLOY_LOG")"
    exec > >(tee -a "$DEPLOY_LOG") 2>&1
    echo "=== dev-deploy $(date -Is) — journal : ${DEPLOY_LOG} ==="
fi

# --- 0 bis) Bootstrap de la deploy key (dépôt privé) ---
# La clé est générée SUR L'HÔTE et jamais collée depuis ailleurs : une clé privée
# ne doit transiter par aucun canal (chat, transcript, log), et un copier-coller
# la casse typiquement en « error in libcrypto ». On n'affiche que la publique.
if [[ "$BOOTSTRAP_KEY" -eq 1 ]]; then
    mkdir -p /root/.ssh && chmod 700 /root/.ssh
    if [[ -f "$DEPLOY_KEY" && "$FORCE" -eq 1 ]]; then
        echo "--force : régénération de la deploy key existante."
        rm -f "$DEPLOY_KEY" "${DEPLOY_KEY}.pub"
    fi
    if [[ ! -f "$DEPLOY_KEY" ]]; then
        ssh-keygen -t ed25519 -N "" -C "roles-deploy@$(hostname)" -f "$DEPLOY_KEY" >/dev/null
        echo "Deploy key générée : ${DEPLOY_KEY}"
    else
        # Idempotent : relancé sans --force, on réaffiche au lieu de régénérer —
        # régénérer invaliderait la clé déjà enregistrée côté GitHub.
        echo "Deploy key déjà présente : ${DEPLOY_KEY} (--force pour régénérer)"
    fi
    if ! grep -q "IdentityFile ${DEPLOY_KEY}" /root/.ssh/config 2>/dev/null; then
        printf 'Host github.com\n  IdentityFile %s\n  IdentitiesOnly yes\n' "$DEPLOY_KEY" \
            >> /root/.ssh/config
        chmod 600 /root/.ssh/config
        echo "SSH configuré pour github.com via cette clé."
    fi
    ssh-keyscan -H github.com >> /root/.ssh/known_hosts 2>/dev/null
    sort -u -o /root/.ssh/known_hosts /root/.ssh/known_hosts
    # Clé publique affichée EN DERNIER : c'est ce que l'opérateur doit copier.
    echo
    echo "=== Clé publique à enregistrer dans GitHub → Settings → Deploy keys (lecture seule) ==="
    cat "${DEPLOY_KEY}.pub"
    echo "========================================================================================"
    echo "Enregistre-la, puis relance : sudo ./dev-deploy.sh <branche>"
    exit 0
fi

# --- 1) Positionnement dans le repo (mode "dans le repo" ou "bootstrap clone") ---
# git fetch + reset --hard plutôt que pull --ff-only : on veut l'état exact de
# la branche distante, modifications locales écrasées.
# Réseau et accès au dépôt sont donc un PRÉREQUIS : il n'existe pas de mode
# « déploie ce qui est déjà là ». Sur dépôt privé sans deploy key, lancer
# d'abord `sudo ./dev-deploy.sh --bootstrap-deploy-key`.
# Branche = argument $1, sinon branche courante détectée.
if [ -d ".git" ]; then
  BRANCH="${1:-$(git branch --show-current)}"
  [ -z "$BRANCH" ] && BRANCH="main"
  echo "Repo détecté dans le répertoire courant: $(pwd)"
  echo "Mise à jour (fetch + reset --hard) sur ${BRANCH}..."
  git fetch origin "$BRANCH"
  DIRTY="$(git status --porcelain)"
  if [ -n "$DIRTY" ]; then
    echo "ATTENTION : modifications locales non commitées, elles vont être écrasées :" >&2
    echo "$DIRTY" >&2
  fi
  HEAD_BEFORE="$(git rev-parse HEAD)"
  git reset --hard "origin/${BRANCH}"
  # Se ré-exécuter si le reset a changé quelque chose. Bash relit le fichier du
  # script en cours de route : poursuivre après s'être réécrit soi-même exécute
  # un mélange des deux versions. Et sans ré-exécution on déploierait du code
  # neuf avec un script, un compose et un build.sh périmés — pannes
  # incompréhensibles garanties. ROLES_REEXEC borne la récursion à un tour.
  if [ "$HEAD_BEFORE" != "$(git rev-parse HEAD)" ] && [ -z "${ROLES_REEXEC:-}" ]; then
    echo "Le dépôt a changé (${HEAD_BEFORE:0:8} -> $(git rev-parse --short HEAD))."
    echo "Ré-exécution dans la version fraîchement récupérée..."
    export ROLES_REEXEC=1
    # --no-hangup-guard à la ré-exécution : le filet est DÉJÀ posé et survit à
    # l'exec (un signal mis à SIG_IGN le reste à travers exec, et le tee est
    # hérité par les descripteurs). Le repasser ouvrirait un second tee sur le
    # même fichier, donc des lignes en double.
    exec bash "$0" "$@" --no-hangup-guard
  fi
else
  APP_DIR="roles"
  if [ -d "$APP_DIR/.git" ]; then
    BRANCH="${1:-$(git -C "$APP_DIR" branch --show-current)}"
    [ -z "$BRANCH" ] && BRANCH="main"
    echo "Repo déjà cloné dans ./${APP_DIR}"
    echo "Mise à jour (fetch + reset --hard) sur ${BRANCH}..."
    git -C "$APP_DIR" fetch origin "$BRANCH"
    DIRTY="$(git -C "$APP_DIR" status --porcelain)"
    if [ -n "$DIRTY" ]; then
      echo "ATTENTION : modifications locales non commitées, elles vont être écrasées :" >&2
      echo "$DIRTY" >&2
    fi
    git -C "$APP_DIR" reset --hard "origin/${BRANCH}"
  else
    echo "Clone du repo dans ./${APP_DIR}..."
    git clone "$REPO_URL" "$APP_DIR"
    if [ -n "${1:-}" ]; then
      git -C "$APP_DIR" checkout "$1"
    fi
  fi
  cd "$APP_DIR"
fi

ENV_FILE=".env"

# --- 2) .env ---
if [ ! -f "$ENV_FILE" ] && [ -f ".env.example" ]; then
  echo ".env absent -> création depuis .env.example"
  cp .env.example "$ENV_FILE"
fi

# --- 3) Complétion des secrets manquants ou vides ---
# Chaque secret est vérifié individuellement : le .env peut exister mais
# avoir des valeurs vides, ou porter le placeholder générique
# "changeme_in_real_env" copié tel quel depuis .env.example.

_env_get() { grep -m1 "^${1}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true; }
_env_set() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else
        echo "${key}=${val}" >> "$ENV_FILE"
    fi
}
_env_needs_generation() {
    local val
    val="$(_env_get "$1")"
    # Les indirections '${vault://...}' des anciens .env ne sont plus résolues
    # depuis la refonte self-service : un tel litéral doit être régénéré,
    # sinon il deviendrait la valeur effective du secret.
    [[ -z "$val" || "$val" == "changeme_in_real_env" || "$val" == *'${vault://'* ]]
}

if _env_needs_generation POSTGRES_USER || _env_needs_generation POSTGRES_PASSWORD; then
    PG_USER="rb_$(openssl rand -hex 4)"
    PG_PASS="$(openssl rand -hex 24)"
    PG_PORT="$(_env_get POSTGRES_PORT)"; PG_PORT="${PG_PORT:-5432}"
    PG_DB="$(_env_get POSTGRES_DB)"; PG_DB="${PG_DB:-role_builder}"
    DB_URL="postgresql://${PG_USER}:${PG_PASS}@localhost:${PG_PORT}/${PG_DB}"
    _env_set POSTGRES_USER     "$PG_USER"
    _env_set POSTGRES_PASSWORD "$PG_PASS"
    _env_set DATABASE_URL      "$DB_URL"
    echo "==> POSTGRES_USER/PASSWORD générés (${PG_USER})"
fi

if _env_needs_generation MINIO_ROOT_USER || _env_needs_generation MINIO_ROOT_PASSWORD; then
    MINIO_USER="minioadmin_$(openssl rand -hex 4)"
    MINIO_PASS="$(openssl rand -hex 24)"
    _env_set MINIO_ROOT_USER     "$MINIO_USER"
    _env_set MINIO_ROOT_PASSWORD "$MINIO_PASS"
    echo "==> MINIO_ROOT_USER/PASSWORD générés (${MINIO_USER})"
fi

if _env_needs_generation LOCAL_ADMIN_SECRET; then
    _env_set LOCAL_ADMIN_SECRET "$(openssl rand -hex 32)"
    echo "==> LOCAL_ADMIN_SECRET généré"
fi

if _env_needs_generation LOCAL_ADMIN_PASSWORD; then
    _env_set LOCAL_ADMIN_PASSWORD "$(openssl rand -hex 12)"
    echo "==> LOCAL_ADMIN_PASSWORD généré"
fi

if _env_needs_generation NEXTAUTH_SECRET; then
    _env_set NEXTAUTH_SECRET "$(openssl rand -hex 32)"
    echo "==> NEXTAUTH_SECRET généré"
fi

# KEYCLOAK_CLIENT_SECRET est un prérequis externe (jamais généré ici) : si
# l'ancien .env porte encore une indirection vault, on la vide + warning.
if [[ "$(_env_get KEYCLOAK_CLIENT_SECRET)" == *'${vault://'* ]]; then
    _env_set KEYCLOAK_CLIENT_SECRET ""
    echo "ATTENTION : KEYCLOAK_CLIENT_SECRET portait une indirection vault" >&2
    echo "obsolète — vidé. Renseigner la vraie valeur si l'auth Keycloak est utilisée." >&2
fi

# Clé Fernet (32 octets base64 url-safe) : chiffre les secrets utilisateur
# stockés en base (tokens de wallets Harpocrate + secrets "local").
if _env_needs_generation SECRET_ENCRYPTION_KEY; then
    _env_set SECRET_ENCRYPTION_KEY "$(openssl rand -base64 32 | tr '+/' '-_')"
    echo "==> SECRET_ENCRYPTION_KEY générée"
fi

unset -f _env_needs_generation

# --- 4) Build images locales ---
# build.sh ne lit que l'env du shell, pas .env : on lui passe l'IMAGE_TAG de
# .env pour qu'il tague les images comme le compose les attend au `up`, sinon
# `up --pull never` échoue « image not found » (BUG-59).
IMAGE_TAG="$(_env_get IMAGE_TAG)"; export IMAGE_TAG="${IMAGE_TAG:-latest}"
chmod +x build.sh
./build.sh

# --- 5) Nettoyage containers orphelins / anciennes runs du projet ---
# down supprime les containers du projet + réseaux, et --remove-orphans enlève ceux qui traînent
echo "Arrêt/cleanup du projet docker compose (incl. orphelins)..."
docker compose -f docker-compose-dev.yml down --remove-orphans || true

# --- 5 bis) Résolution des ports, APRÈS l'arrêt de la stack ---
# L'ordre n'est pas négociable : sonder un port AVANT le `down` ferait détecter
# notre propre service comme un conflit. Le repli s'appliquerait alors à tort,
# se persisterait dans .env, et l'URL publiée pointerait dans le vide.
#
# Les machines de test sont partagées : host-test-23 porte six projets compose
# (portail devpod, harpocrate, Zulip, observabilité, browserless) et 8000, 5432
# et 3000 y sont déjà pris. Les ports doivent donc se paramétrer, pas se
# supposer.
#
# Deux cas, et ils ne se traitent pas pareil :
#  - l'opérateur a posé une valeur NON par défaut dans .env => elle est
#    respectée, et si elle est occupée on ÉCHOUE. Déplacer en silence un port
#    choisi casserait ce qui en dépend (reverse-proxy, exposition déclarée à
#    l'annuaire du portail) ;
#  - la valeur est celle par défaut (ou absente) => on sonde, et on bascule sur
#    le premier port libre à partir de DEFAUT+10000, puis on le PERSISTE dans
#    .env pour que le choix survive au redéploiement.

# ss -H : pas d'en-tête. La colonne 4 porte l'adresse locale, donc on matche la
# fin ":<port>" — un service lié à 127.0.0.1 est un conflit comme un autre pour
# une publication sur 0.0.0.0.
_port_in_use() {
    ss -ltnH 2>/dev/null | awk -v p=":$1\$" '$4 ~ p { found = 1 } END { exit !found }'
}

_first_free_port() {
    local candidate="$1" ceiling=$(( $1 + 200 ))
    while [ "$candidate" -lt "$ceiling" ]; do
        _port_in_use "$candidate" || { printf '%s' "$candidate"; return 0; }
        candidate=$(( candidate + 1 ))
    done
    return 1
}

# Mémoire des replis que LE SCRIPT a attribués. Sans elle, un port de repli
# persisté dans .env est indiscernable d'un port choisi par un humain : au
# déploiement suivant le script le respecterait et échouerait si entre-temps il
# a été pris, au lieu de re-résoudre. On enregistre donc la VALEUR attribuée —
# si .env porte encore exactement cette valeur, elle est à nous ; si elle
# diffère, c'est qu'un humain est passé derrière, et elle prime.
_auto_recorded() { grep -m1 "^${1}=" "$AUTO_PORTS" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true; }
_auto_record() {
    mkdir -p "$(dirname "$AUTO_PORTS")"; touch "$AUTO_PORTS"
    if grep -q "^${1}=" "$AUTO_PORTS"; then
        sed -i "s|^${1}=.*|${1}=${2}|" "$AUTO_PORTS"
    else
        echo "${1}=${2}" >> "$AUTO_PORTS"
    fi
}
_auto_forget() { [ -f "$AUTO_PORTS" ] && sed -i "/^${1}=/d" "$AUTO_PORTS" || true; }

# $1 = nom de la variable, $2 = valeur par défaut du compose
_resolve_port() {
    local var="$1" default="$2" current recorded resolved
    current="$(_env_get "$var")"
    recorded="$(_auto_recorded "$var")"

    # Cas 1 — valeur posée par un humain (ni le défaut, ni un de nos replis).
    if [ -n "$current" ] && [ "$current" != "$default" ] && [ "$current" != "$recorded" ]; then
        if _port_in_use "$current"; then
            echo "ÉCHEC : ${var}=${current} est imposé dans .env mais le port est occupé par :" >&2
            ss -ltnp 2>/dev/null | awk -v p=":${current}\$" '$4 ~ p' >&2
            echo "Choisir un autre port dans .env, ou libérer celui-ci." >&2
            exit 1
        fi
        _auto_forget "$var"
        echo "  ${var}=${current} (imposé dans .env, libre)"
        return 0
    fi

    # Cas 2 — un repli que nous avons attribué. On le GARDE tant qu'il est libre :
    # faire revenir le port au défaut dès qu'il se libère déplacerait l'URL
    # publiée sous les pieds de ce qui l'utilise. La stabilité prime.
    if [ -n "$recorded" ] && [ "$current" = "$recorded" ]; then
        if ! _port_in_use "$current"; then
            echo "  ${var}=${current} (repli attribué précédemment, toujours libre)"
            return 0
        fi
        echo "  ${var} : le repli ${current} est désormais occupé, nouvelle résolution..."
    fi

    # Cas 3 — le défaut est libre.
    if ! _port_in_use "$default"; then
        _env_set "$var" "$default"
        _auto_forget "$var"
        echo "  ${var}=${default} (défaut, libre)"
        return 0
    fi

    # Cas 4 — repli, persisté dans .env ET enregistré comme étant le nôtre.
    resolved="$(_first_free_port $(( default + 10000 )))" || {
        echo "ÉCHEC : aucun port libre trouvé pour ${var} à partir de $(( default + 10000 ))." >&2
        exit 1
    }
    _env_set "$var" "$resolved"
    _auto_record "$var" "$resolved"
    echo "  ${var}=${resolved} (repli : ${default} est occupé, valeur persistée dans .env)"
}

echo "Résolution des ports (après arrêt de la stack)..."
_resolve_port POSTGRES_PORT      5432
_resolve_port MINIO_API_PORT     9000
_resolve_port MINIO_CONSOLE_PORT 9001
_resolve_port BACKEND_PORT       8000
_resolve_port FRONTEND_PORT      3000

# --- 5 ter) Tirer les images TIERCES, avant le `up --pull never` ---
# `--pull never` au `up` est volontaire : il garantit qu'on démarre exactement
# les images que build.sh vient de construire, et jamais une homonyme tirée d'un
# registre. Mais il bloque du même coup les images tierces — postgres, minio —
# que personne ne construit ici : le `up` échoue alors sur
# « No such image: minio/minio:latest ».
#
# Découvert au PREMIER déploiement réel (test1, 2026-10-08). Le défaut était
# invisible jusque-là, et il l'était doublement : sur cet hôte partagé,
# postgres:16-alpine se trouvait déjà présente — tirée par une autre stack — si
# bien que seule minio manquait. Sur une machine vierge, les deux manqueraient.
#
# On tire donc explicitement, par NOM DE SERVICE compose et non par nom d'image,
# pour que la version reste déclarée au seul endroit qui fait foi : le compose.
# TOUTE nouvelle dépendance tierce doit être ajoutée à cette liste, sinon elle
# reproduira exactement cette panne.
echo "Tirage des images tierces (postgres, minio)..."
docker compose -f docker-compose-dev.yml pull postgres minio

# --- 6) Relance ---
# --remove-orphans : supprime les orphelins détectés
# --pull never : utilise les images locales buildées à l'étape 4
echo "Démarrage docker compose..."
docker compose -f docker-compose-dev.yml up -d --remove-orphans --pull never

# --- 7) Smoke test /health (timeout 90s) + tail des logs ---
BACKEND_PORT="$(_env_get BACKEND_PORT)"; BACKEND_PORT="${BACKEND_PORT:-8000}"
HEALTH_URL="http://localhost:${BACKEND_PORT}/health/"

echo "Smoke test : ${HEALTH_URL} (timeout 90s)..."
START="$SECONDS"
until curl -sf "$HEALTH_URL" >/dev/null 2>&1; do
    if [ "$((SECONDS - START))" -ge 90 ]; then
        echo "ÉCHEC : ${HEALTH_URL} ne répond pas après 90s." >&2
        docker compose -f docker-compose-dev.yml logs --tail=100
        exit 1
    fi
    sleep 2
done
echo "OK : backend healthy (${SECONDS}s)."
docker compose -f docker-compose-dev.yml logs --tail=50

# --- 8) Récupération d'espace disque, au plus une fois par semaine ---
# Chaque déploiement reconstruit les images : les couches précédentes sont
# détaggées mais restent décompressées, et rien ne les récupère. Une machine qui
# déploie plusieurs fois par jour sature son disque en quelques semaines — et
# une machine sans espace n'arrive plus à relancer la stack qu'elle vient
# d'arrêter, en plein déploiement.
# Quatre bornes, toutes nécessaires :
#  - fréquence : témoin horodaté, une purge par semaine au plus (purger à chaque
#    passage ajoute des minutes, et finit par être désactivée « le temps de ») ;
#  - position : APRÈS le contrôle de santé, pour ne pas retarder la mise à dispo ;
#  - portée : cache de construction INUTILISÉ DEPUIS 7 JOURS + images détaggées
#    seulement. Jamais de purge globale (elle supprimerait les images de base) ni
#    de volumes (données) ;
#  - code de retour : un échec de purge ne fait jamais échouer le déploiement.
#
# Pourquoi `--filter until=168h` et PAS `builder prune -af` : le cache de
# construction est à l'échelle du démon Docker, pas du projet compose. Les
# machines de test sont partagées — `test1` (host-test-23) porte le portail
# devpod, harpocrate, Zulip et la stack d'observabilité, soit six projets
# compose et 2,4 Go de cache commun. Un `-a` viderait le cache de TOUS ces
# projets et ralentirait leur prochaine construction, pour un bénéfice qui ne
# concerne que nous. Le filtre de date ne ramasse que ce que plus personne ne
# réutilise, ce qui est exactement l'intention de la garde.
mkdir -p "$(dirname "$PURGE_STAMP")"
PURGE_DUE=1
if [ -f "$PURGE_STAMP" ]; then
    # -mtime +7 : plus vieux que 7 jours. Témoin absent => on purge, sans échouer.
    [ -z "$(find "$PURGE_STAMP" -mtime +7 -print 2>/dev/null)" ] && PURGE_DUE=0
fi
if [ "$PURGE_DUE" -eq 1 ]; then
    echo "Purge hebdomadaire (cache inutilisé depuis 7j + images détaggées)..."
    {
        docker builder prune -f --filter until=168h
        docker image prune -f
    } 2>&1 | grep -iE "reclaimed|Total" || true
    date -Is > "$PURGE_STAMP"
else
    echo "Purge disque : ignorée (dernière il y a moins de 7 jours)."
fi
