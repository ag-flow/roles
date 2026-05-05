# Role Builder

Webapp pour construire des rôles ag.flow à partir de corpus audio scrapés
(YouTube / Instagram / TikTok). Pipeline complet : scraping → transcription →
chunking + embeddings → synthèse Mistral en 4 étages → export vers ag.flow.

## Documentation

- **Spec produit complète** : `docs/specs/00-overview.md` (point d'entrée)
- **Modèle de données** : `docs/specs/01-data-model.md`
- **Plans d'implémentation** : `docs/superpowers/plans/`
- **Instructions Claude Code** : `CLAUDE.md`

# 🚀 Installation & Déploiement (Repository privé via SSH)

Ce guide explique comment :
- configurer l’accès SSH à GitHub
- cloner le repository privé
- initialiser l’environnement
- builder et lancer l’application

---

## 🔐 1. Configurer l’accès SSH à GitHub

### 1.1 Générer une clé SSH

Sur la machine cible :

```bash
ssh-keygen -t ed25519 -C "deploy-roles"
```

Appuyer sur Entrée pour accepter le chemin par défaut :
```bash
~/.ssh/id_ed25519
```

Passphrase :
- laisser vide pour un serveur (déploiement automatique)
- ou en définir une pour plus de sécurité

Démarrer l’agent SSH et charger la clé
```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

cat ~/.ssh/id_ed25519.pub

```



1 - Ajouter la clé dans GitHub
2 - Aller sur GitHub
3 - Settings
4 - (SSH and GPG keys)[https://github.com/settings/keys]
5 - New SSH key
6 - Name : deploy-roles
7 - Coller la clé publique
8 - Cliquer sur Add SSH key


Tester la connexion
```bash
ssh -T git@github.com
```

Cloner le repository
```bash
git clone git@github.com:ag-flow/roles.git
cd roles
```

Affiche les logs
```bash
docker compose -f docker-compose-dev.yml logs --tail=50 backend
docker compose -f docker-compose-dev.yml logs --tail=50 frontend
```
