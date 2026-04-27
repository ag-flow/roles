# Role Builder

Webapp pour construire des rôles ag.flow à partir de corpus audio scrapés
(YouTube / Instagram / TikTok). Pipeline complet : scraping → transcription →
chunking + embeddings → synthèse Mistral en 4 étages → export vers ag.flow.

## Documentation

- **Spec produit complète** : `docs/specs/00-overview.md` (point d'entrée)
- **Modèle de données** : `docs/specs/01-data-model.md`
- **Plans d'implémentation** : `docs/superpowers/plans/`
- **Instructions Claude Code** : `CLAUDE.md`

## Démarrage rapide

```bash
cp .env.example .env                              # Adapter les valeurs si nécessaire
docker compose up -d                              # Lance toute la stack
./scripts/apply_migrations.sh                     # Applique les migrations SQL
./scripts/init_minio.sh                           # Crée les buckets
./scripts/init_openbao.sh                         # Active KV v2

curl http://localhost:8000/health/                # Health-check backend
open http://localhost:3000                        # Interface
```

## Stack

Backend FastAPI + asyncpg | Frontend Next.js 14 | PostgreSQL 16 + pgvector |
MinIO | OpenBao | Mistral via ag.flow.
