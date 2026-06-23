# GUIDE DE DÉPLOIEMENT – DIGITRANS-CM
## CRM API SavoirManger (AGROCAM S.A.)

---

## Table des matières

1. [Prérequis](#1-prérequis)
2. [Déploiement local (développement)](#2-déploiement-local-développement)
3. [Déploiement Cloud – Infrastructure (Terraform)](#3-déploiement-cloud--infrastructure-terraform)
4. [Déploiement de l'application sur AKS](#4-déploiement-de-lapplication-sur-aks)
5. [Pipeline CI/CD GitHub Actions](#5-pipeline-cicd-github-actions)
6. [Vérification de la solution](#6-vérification-de-la-solution)
7. [Pousser sur votre dépôt GitHub](#7-pousser-sur-votre-dépôt-github)

---

## 1. Prérequis

### Outils à installer

| Outil          | Version min. | Lien de téléchargement                         | Vérification           |
|---------------|-------------|------------------------------------------------|------------------------|
| Git            | 2.40        | https://git-scm.com/download/win               | `git --version`        |
| Docker Desktop | 4.28        | https://www.docker.com/products/docker-desktop | `docker --version`     |
| Python         | 3.12        | https://www.python.org/downloads/              | `python --version`     |
| Terraform      | 1.7         | https://developer.hashicorp.com/terraform/install | `terraform -version` |
| Azure CLI      | 2.58        | https://learn.microsoft.com/cli/azure/install-azure-cli | `az --version` |
| kubectl        | 1.28        | https://kubernetes.io/docs/tasks/tools/        | `kubectl version`      |
| GitHub CLI     | 2.45        | https://cli.github.com/                        | `gh --version`         |

### Comptes nécessaires

- Compte **GitHub** (pour héberger le dépôt)
- Compte **Azure** avec abonnement actif (pour le déploiement cloud)
- Compte **AWS** avec accès programmatique (pour le cluster BI)

---

## 2. Déploiement local (développement)

C'est la voie la plus rapide pour voir la solution fonctionner **sans aucun compte cloud**.

### Étape 1 – Cloner le dépôt

```bash
git clone https://github.com/VOTRE_USERNAME/digitrans-cm.git
cd digitrans-cm
```

### Étape 2 – Lancer la stack complète

```bash
docker compose up -d
```

Cette commande démarre automatiquement :
- **CRM API** (FastAPI) → port 8000
- **PostgreSQL 15** → port 5432
- **Redis 7** → port 6379
- **Prometheus** → port 9090
- **Grafana** → port 3001

### Étape 3 – Vérifier que tout fonctionne

```bash
# Santé de l'API
curl http://localhost:8000/health

# Réponse attendue :
# {"status":"healthy","service":"crm-api","version":"1.0.0","redis":"ok"}
```

Ouvrir dans le navigateur :
- **API (documentation interactive)** → http://localhost:8000/api/docs
- **Grafana (métriques)** → http://localhost:3001 (admin / admin123)
- **Prometheus** → http://localhost:9090

### Étape 4 – Tester l'API

```bash
# 1. Créer un client
curl -X POST http://localhost:8000/api/v1/clients/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer VOTRE_TOKEN" \
  -d '{
    "nom": "MOUKAM",
    "prenom": "Jean-Claude",
    "telephone": "+237699000001",
    "email": "jc.moukam@agrocam.cm",
    "ville": "Douala",
    "quartier": "Bonanjo",
    "consentement_marketing": true
  }'

# 2. Lister les clients
curl http://localhost:8000/api/v1/clients/ \
  -H "Authorization: Bearer VOTRE_TOKEN"

# 3. Créer une commande (mode sur place)
curl -X POST http://localhost:8000/api/v1/commandes/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer VOTRE_TOKEN" \
  -d '{
    "restaurant_id": "SM-DLA-01",
    "mode": "sur_place",
    "lignes": [
      {
        "article_id": "MENU-001",
        "article_nom": "Menu Poulet DG",
        "quantite": 2,
        "prix_unitaire": 3500
      },
      {
        "article_id": "BOISSON-004",
        "article_nom": "Jus de Goyave",
        "quantite": 2,
        "prix_unitaire": 500
      }
    ],
    "mode_paiement": "mobile_money"
  }'

# 4. Tester la synchronisation offline
curl -X POST http://localhost:8000/api/v1/sync/batch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer VOTRE_TOKEN" \
  -d '{
    "device_id": "CAISSE-DLA-01-POS",
    "last_sync_at": "2026-06-23T08:00:00Z",
    "operations": [
      {
        "type": "create_commande",
        "local_id": "offline-abc123",
        "created_at_local": "2026-06-23T10:30:00Z",
        "device_id": "CAISSE-DLA-01-POS",
        "restaurant_id": "SM-DLA-01",
        "payload": {
          "restaurant_id": "SM-DLA-01",
          "mode": "a_emporter",
          "lignes": [
            {
              "article_id": "MENU-002",
              "article_nom": "Brochettes de boeuf",
              "quantite": 3,
              "prix_unitaire": 2000
            }
          ]
        }
      }
    ]
  }'
```

### Étape 5 – Arrêter la stack

```bash
docker compose down           # arrête et supprime les conteneurs
docker compose down -v        # arrête + supprime les volumes (données)
```

---

## 3. Déploiement Cloud – Infrastructure (Terraform)

> Nécessite un abonnement Azure actif et un compte AWS.

### Étape 1 – Authentification

```bash
# Azure
az login
az account set --subscription "VOTRE_SUBSCRIPTION_ID"

# AWS
aws configure
# AWS Access Key ID: VOTRE_ACCESS_KEY
# AWS Secret Access Key: VOTRE_SECRET_KEY
# Default region name: af-south-1
```

### Étape 2 – Créer le backend Terraform (stockage de l'état)

```bash
# Créer le groupe de ressources et le compte de stockage pour l'état Terraform
az group create --name digitrans-tfstate-rg --location egyptcentral

az storage account create \
  --name digitranstfstateprod \
  --resource-group digitrans-tfstate-rg \
  --location egyptcentral \
  --sku Standard_LRS \
  --encryption-services blob \
  --min-tls-version TLS1_2

az storage container create \
  --name tfstate \
  --account-name digitranstfstateprod
```

### Étape 3 – Configurer les variables sensibles

Créer le fichier `infrastructure/terraform/environments/prod/terraform.tfvars` :

> **ATTENTION** : ce fichier est dans `.gitignore` — ne jamais le commiter.

```hcl
# infrastructure/terraform/environments/prod/terraform.tfvars

tenant_id                  = "VOTRE_TENANT_ID"
app_service_principal_id   = "VOTRE_SP_OBJECT_ID"
db_admin_user              = "digitransadmin"
db_admin_password          = "VotreMotDePasse!2026"
bi_db_user                 = "biadmin"
bi_db_password             = "VotreMotDePasse!BI2026"
aws_kms_key_arn            = "arn:aws:kms:af-south-1:COMPTE:key/VOTRE_KEY_ID"
redis_backup_storage_connection = "DefaultEndpointsProtocol=https;AccountName=..."
```

### Étape 4 – Déployer l'infrastructure

```bash
cd infrastructure/terraform/environments/prod

# Initialiser Terraform
terraform init

# Vérifier le plan (aucune ressource créée)
terraform plan -var-file="terraform.tfvars" -out=tfplan

# Déployer (durée estimée : 15-25 minutes)
terraform apply tfplan
```

### Étape 5 – Récupérer les outputs

```bash
terraform output
# Exemples de valeurs récupérées :
# aks_cluster_name = "digitrans-cm-prod-aks"
# redis_hostname   = "digitrans-cm-prod-redis.redis.cache.windows.net"
# pg_fqdn          = "digitrans-cm-prod-pgflex.postgres.database.azure.com"
# agw_public_ip    = "20.X.X.X"
```

---

## 4. Déploiement de l'application sur AKS

### Étape 1 – Construire et pousser l'image Docker

```bash
# Se connecter au registre de conteneurs Azure (ACR)
az acr login --name digitranscr

# Construire l'image
cd services/crm-api
docker build -t digitranscr.azurecr.io/crm-api:1.0.0 .

# Scanner l'image avant push
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:latest image \
  --severity CRITICAL,HIGH \
  digitranscr.azurecr.io/crm-api:1.0.0

# Pousser l'image
docker push digitranscr.azurecr.io/crm-api:1.0.0
```

### Étape 2 – Configurer kubectl pour AKS

```bash
az aks get-credentials \
  --resource-group digitrans-cm-prod-rg \
  --name digitrans-cm-prod-aks \
  --overwrite-existing

# Vérifier la connexion
kubectl get nodes
```

### Étape 3 – Créer le namespace et les secrets Kubernetes

```bash
# Créer le namespace applicatif
kubectl create namespace digitrans

# Remplacer les variables dans le SecretProviderClass
export AZURE_CLIENT_ID=$(terraform output -raw aks_principal_id)
export AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)

envsubst < infrastructure/kubernetes/secrets/secret-provider-class.yaml \
  | kubectl apply -f -
```

### Étape 4 – Déployer l'application

```bash
# Déployer dans l'ordre : secrets → service → déploiement
kubectl apply -f infrastructure/kubernetes/secrets/secret-provider-class.yaml
kubectl apply -f infrastructure/kubernetes/services/crm-api.yaml
kubectl apply -f infrastructure/kubernetes/deployments/crm-api.yaml

# Surveiller le déploiement
kubectl rollout status deployment/crm-api -n digitrans --timeout=300s

# Vérifier les pods
kubectl get pods -n digitrans -w
```

### Étape 5 – Vérifier le déploiement

```bash
# État général
kubectl get all -n digitrans

# Logs de l'application
kubectl logs -n digitrans -l app=crm-api --tail=50 -f

# Tester via port-forward (sans exposer publiquement)
kubectl port-forward -n digitrans svc/crm-api-svc 8080:80
curl http://localhost:8080/health

# Voir les métriques HPA
kubectl get hpa -n digitrans
```

---

## 5. Pipeline CI/CD GitHub Actions

Le pipeline se déclenche automatiquement. Voici la configuration des secrets GitHub nécessaires.

### Secrets à configurer dans GitHub

Aller dans : **Dépôt GitHub → Settings → Secrets and variables → Actions**

| Secret                      | Description                          | Comment l'obtenir                          |
|-----------------------------|--------------------------------------|--------------------------------------------|
| `AZURE_CLIENT_ID`           | ID du Service Principal OIDC         | `az ad sp show --id NOM --query appId`    |
| `AZURE_TENANT_ID`           | ID du tenant Azure AD                | `az account show --query tenantId`        |
| `AZURE_SUBSCRIPTION_ID`     | ID de l'abonnement Azure             | `az account show --query id`              |
| `STAGING_API_URL`           | URL de l'API staging                 | Adresse IP Application Gateway staging    |
| `PROD_API_URL`              | URL de l'API production              | Adresse IP Application Gateway prod       |
| `SLACK_WEBHOOK_CAMTECH`     | Webhook Slack pour les notifications | Slack → Apps → Incoming Webhooks          |
| `SEMGREP_APP_TOKEN`         | Token Semgrep (optionnel)            | https://semgrep.dev                        |

### Configurer la Workload Identity Federation (OIDC)

```bash
# Créer l'application Azure AD pour GitHub Actions
az ad app create --display-name "digitrans-cm-github-actions"

APP_ID=$(az ad app list --display-name "digitrans-cm-github-actions" \
  --query "[0].appId" -o tsv)

az ad sp create --id $APP_ID

# Ajouter la fédération OIDC pour GitHub
az ad app federated-credential create \
  --id $APP_ID \
  --parameters '{
    "name": "github-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:VOTRE_USERNAME/digitrans-cm:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'

# Donner les permissions nécessaires
az role assignment create \
  --assignee $APP_ID \
  --role "Contributor" \
  --scope "/subscriptions/VOTRE_SUBSCRIPTION_ID"

echo "AZURE_CLIENT_ID = $APP_ID"
```

### Configurer les environnements GitHub avec approbation

Aller dans : **Dépôt → Settings → Environments**

1. Créer l'environnement `staging` : aucune approbation requise
2. Créer l'environnement `production` : ajouter des **Required reviewers** (vous + un collègue)

### Déclenchement manuel

```bash
# Via GitHub CLI
gh workflow run cd.yml --field environment=staging

# Voir l'état du pipeline
gh run list --workflow=ci.yml
gh run watch
```

---

## 6. Vérification de la solution finale

### Tests de l'API en production

```bash
API_URL="https://20.X.X.X"  # Remplacer par votre IP Application Gateway

# Health check
curl -k https://${API_URL}/health | jq .

# Vérifier les headers de sécurité
curl -I https://${API_URL}/health | grep -E "Strict-Transport|X-Content|X-Frame|Content-Security"
```

### Résultats attendus

```json
// GET /health
{
  "status": "healthy",
  "service": "crm-api",
  "version": "1.0.0",
  "redis": "ok"
}
```

```
// Headers de sécurité attendus
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; ...
```

### Vérifications infrastructure

```bash
# AKS – état du cluster
kubectl get nodes -n digitrans
kubectl get hpa -n digitrans
kubectl get pdb -n digitrans

# Terraform – état de l'infrastructure
cd infrastructure/terraform/environments/prod
terraform show

# WAF – logs de filtrage
az network application-gateway waf-policy list \
  --resource-group digitrans-cm-prod-rg

# Coût estimé de l'infrastructure
az consumption usage list \
  --start-date 2026-06-01 \
  --end-date 2026-06-23 \
  --output table
```

---

## 7. Pousser sur votre dépôt GitHub

### Option A – Créer un nouveau dépôt (recommandé)

```bash
# 1. Se connecter à GitHub
gh auth login

# 2. Aller dans le dossier du projet
cd C:\Users\DIALLO\digitrans-cm

# 3. Initialiser le dépôt git local
git init
git add .
git commit -m "feat: initialisation projet DIGITRANS-CM

Architecture hybride cloud Azure/AWS pour AGROCAM S.A.
- Infrastructure as Code (Terraform)
- CRM API microservice (FastAPI, offline-first)
- Orchestration Kubernetes (AKS)
- Pipeline CI/CD GitHub Actions (SAST + DAST + deploy)
- Rapport de sécurisation complet

Co-Authored-By: CAMTECH-SOLUTIONS <noreply@camtech-solutions.cm>"

# 4. Créer le dépôt sur GitHub et pousser
gh repo create digitrans-cm \
  --private \
  --description "DIGITRANS-CM – Système d'Information Cloud Hybride AGROCAM S.A." \
  --push \
  --source .

# Votre dépôt est maintenant disponible sur :
# https://github.com/VOTRE_USERNAME/digitrans-cm
```

### Option B – Pousser sur un dépôt existant

```bash
cd C:\Users\DIALLO\digitrans-cm

git init
git remote add origin https://github.com/VOTRE_USERNAME/VOTRE_REPO.git
git add .
git commit -m "feat: projet DIGITRANS-CM"
git branch -M main
git push -u origin main
```

### Vérifier après le push

```bash
# Voir les fichiers sur GitHub
gh repo view --web

# Voir les workflows déclenchés
gh run list

# Voir les secrets configurés
gh secret list
```

---

## Récapitulatif de l'architecture déployée

```
GitHub (djamilabeyas/digitrans-cm)
    │
    │ git push → déclenche
    ▼
GitHub Actions CI
    ├── Bandit (SAST Python)
    ├── Semgrep (OWASP patterns)
    ├── Trivy (CVE dépendances + image Docker)
    ├── Tests pytest (couverture > 80%)
    └── Checkov (sécurité IaC Terraform)
                │
                │ merge sur main → déclenche
                ▼
GitHub Actions CD
    ├── Build + Push image → Azure Container Registry
    ├── Deploy → AKS Staging (auto)
    ├── Smoke tests staging
    ├── [APPROBATION MANUELLE]
    └── Deploy → AKS Production (Blue/Green)

                ┌─────────────────────────────┐
                │   AZURE Egypt (egyptcentral) │
                │                             │
Internet ──►  WAF + Application Gateway        │
                │                             │
                ▼                             │
              AKS Cluster                     │
              ├─ crm-api (3→20 pods, HPA)     │
              ├─ PostgreSQL Flexible (HA)     │
              └─ Redis Premium (AOF)          │
                │                             │
                └─────────────────────────────┘
                        │
                        │ Données BI agrégées
                        ▼
                ┌───────────────────┐
                │  AWS af-south-1   │
                │  EKS + Aurora     │
                │  Dashboards BI    │
                └───────────────────┘
```

---

*Guide rédigé par CAMTECH SOLUTIONS S.A. – Projet DIGITRANS-CM – Juin 2026*
