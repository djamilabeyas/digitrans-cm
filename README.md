# DIGITRANS-CM – Digitalisation et Transformation Numérique au Cameroun

**Client** : AGROCAM S.A. | **Prestataire** : CAMTECH SOLUTIONS S.A. | **Période** : 2026-2027

## Architecture globale

```
                        CAMEROUN (on-premise futur)
                        ┌────────────────────────┐
                        │   Données RH / ERP     │
                        │   (serveur local Douala)│
                        └──────────┬─────────────┘
                                   │ VPN site-to-site
                    ┌──────────────┼──────────────┐
                    │                             │
        AZURE EGYPT (egyptcentral)         AWS af-south-1
        ┌─────────────────────────┐    ┌──────────────────────┐
        │  WAF + App Gateway      │    │  EKS Cluster (BI)    │
        │  AKS Cluster            │    │  Aurora PostgreSQL    │
        │  ├─ CRM API             │    │  Dashboards BI        │
        │  ├─ Auth Service        │    │  GuardDuty           │
        │  └─ Supply Chain API    │    │  CloudTrail           │
        │  PostgreSQL Flexible    │    └──────────────────────┘
        │  Azure Cache for Redis  │
        │  Key Vault HSM Premium  │
        └─────────────────────────┘
```

## Structure du dépôt

```
digitrans-cm/
├── infrastructure/
│   ├── terraform/
│   │   ├── modules/
│   │   │   ├── networking/   # VNet Azure + VPC AWS
│   │   │   ├── compute/      # AKS + EKS + Redis
│   │   │   ├── database/     # PostgreSQL Flex + Aurora
│   │   │   └── security/     # WAF, Key Vault, GuardDuty
│   │   └── environments/
│   │       ├── prod/
│   │       └── staging/
│   └── kubernetes/
│       ├── deployments/      # Manifests AKS
│       ├── services/         # Services + NetworkPolicy
│       └── secrets/          # SecretProviderClass (Key Vault CSI)
├── services/
│   └── crm-api/              # Module CRM SavoirManger (FastAPI)
├── .github/workflows/
│   ├── ci.yml                # SAST + Tests + Build + Scan
│   └── cd.yml                # Deploy Staging → Prod (avec approbation)
├── monitoring/               # Prometheus + Grafana
├── scripts/                  # Init DB, utilitaires
└── docs/
    └── rapport-securisation.md  # Rapport de sécurisation (livrable)
```

## Démarrage rapide (développement)

```bash
# Prérequis : Docker Desktop, Python 3.12

# 1. Lancer la stack complète
docker compose up -d

# 2. CRM API disponible sur
curl http://localhost:8000/health

# 3. Grafana : http://localhost:3001 (admin/admin123)
# 4. Prometheus : http://localhost:9090
```

## Déploiement production

```bash
# Prérequis : Terraform >= 1.7, Azure CLI, AWS CLI, kubectl

# 1. Infrastructure
cd infrastructure/terraform/environments/prod
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# 2. Application
# → Automatisé via GitHub Actions CD pipeline
# → Push sur main → Staging auto → Approbation → Production
```

## Livrables du projet DIGITRANS-CM

| # | Livrable                    | Fichier(s)                                      | Statut |
|---|-----------------------------|-------------------------------------------------|--------|
| 1 | Architecture IaC Terraform  | `infrastructure/terraform/`                     | ✅     |
| 2 | Application CRM déployée    | `services/crm-api/`                             | ✅     |
| 3 | Conteneurisation Docker     | `services/crm-api/Dockerfile`, `docker-compose.yml` | ✅ |
| 4 | Orchestration Kubernetes    | `infrastructure/kubernetes/`                    | ✅     |
| 5 | Pipeline CI/CD              | `.github/workflows/`                            | ✅     |
| 6 | Mécanisme offline-first     | `services/crm-api/app/routers/sync.py`          | ✅     |
| 7 | **Rapport de sécurisation** | `docs/rapport-securisation.md`                  | ✅     |

## Conformité

- Loi camerounaise n°2010/012 (cybersécurité et cybercriminalité)
- Données hébergées sur le continent africain (Azure Egypt + AWS Afrique du Sud)
- Rétention logs d'audit : 7 ans (AWS S3 Glacier)
