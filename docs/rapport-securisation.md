# RAPPORT DE SÉCURISATION
## Projet DIGITRANS-CM – Optimisation du SI par le Cloud Computing
### CAMTECH SOLUTIONS S.A. pour AGROCAM S.A.

---

| Champ           | Valeur                                     |
|-----------------|--------------------------------------------|
| **Référence**   | DIGITRANS-CM-SEC-001                       |
| **Version**     | 1.0                                        |
| **Date**        | Juin 2026                                  |
| **Classif.**    | CONFIDENTIEL – Usage interne AGROCAM/CAMTECH |
| **Auteur**      | Expert Cybersécurité – CAMTECH SOLUTIONS   |
| **Client**      | AGROCAM S.A. – M. Henri-Claude MOUKAM, DG |

---

## 1. RÉSUMÉ EXÉCUTIF

Le projet DIGITRANS-CM a pour ambition de moderniser le Système d'Information d'AGROCAM S.A. en migrant vers une architecture hybride cloud (Azure Egypt + AWS Afrique du Sud). Ce rapport présente les mesures de sécurité mises en œuvre, leur justification au regard du contexte réglementaire camerounais, et les recommandations pour maintenir le niveau de sécurité dans la durée.

**Niveau de risque résiduel évalué : FAIBLE** après application de l'ensemble des contrôles décrits dans ce document.

### Synthèse des contrôles appliqués

| Domaine                        | Statut      | Priorité |
|-------------------------------|-------------|----------|
| Chiffrement des données        | ✅ Implémenté | Critique |
| Authentification et RBAC       | ✅ Implémenté | Critique |
| WAF et protection périmétrique | ✅ Implémenté | Critique |
| Souveraineté des données       | ✅ Implémenté | Haute    |
| Audit et traçabilité           | ✅ Implémenté | Haute    |
| CI/CD sécurisé                 | ✅ Implémenté | Haute    |
| Résilience offline-first       | ✅ Implémenté | Haute    |
| Monitoring et détection        | ✅ Implémenté | Moyenne  |
| Gestion des incidents          | 🔄 En cours  | Haute    |
| Tests de pénétration           | 🔄 Planifié  | Haute    |

---

## 2. CADRE RÉGLEMENTAIRE

### 2.1 Loi camerounaise n°2010/012

La loi du 21 décembre 2010 relative à la cybersécurité et à la cybercriminalité impose :

- **Article 6** : Obligation de traçabilité des accès aux systèmes d'information critiques. → Implémenté via `AuditMiddleware` + AWS CloudTrail + Azure Monitor.
- **Article 12** : Protection des données à caractère personnel. → Implémenté via chiffrement au repos (PostgreSQL + KMS), consentement client en base, suppression logique RGPD-compatible.
- **Article 17** : Notification des incidents de sécurité aux autorités compétentes sous 72h. → Procédure documentée en section 8.

### 2.2 Souveraineté des données

Conformément aux exigences du DG d'AGROCAM et aux restrictions légales :

| Type de données           | Localisation                    | Justification                        |
|--------------------------|----------------------------------|--------------------------------------|
| Données RH               | On-premise Douala (futur)        | Données d'identité – loi nationale   |
| Données financières       | Azure Egypt (egyptcentral)       | Plus proche disponible + Azure AD    |
| Données clients CRM       | Azure Egypt (egyptcentral)       | Conformité 2010/012                  |
| Données BI (agrégées)     | AWS af-south-1 (Afrique du Sud)  | Données anonymisées – pas de PII     |
| Logs d'audit              | AWS af-south-1 (retention 7 ans) | Conformité réglementaire             |

**Principe appliqué** : aucune donnée à caractère personnel (PII) ne quitte le continent africain.

---

## 3. ARCHITECTURE DE SÉCURITÉ

### 3.1 Défense en profondeur (Defense in Depth)

L'architecture met en œuvre sept couches de sécurité superposées :

```
Internet
    │
    ▼
┌─────────────────────────────────────────────┐
│  Couche 1 : WAF Azure (OWASP 3.2)           │
│  • Filtrage SQL injection, XSS, RCE         │
│  • Géo-blocage (CM, FR, BE, CH, CI, SN, GA) │
│  • Bot protection Microsoft                 │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Couche 2 : TLS 1.3 + HSTS                  │
│  • Certificat géré Azure Key Vault           │
│  • Renouvellement automatique (J-30)         │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Couche 3 : API Gateway / Rate Limiting      │
│  • 100 req/min par IP                        │
│  • Headers sécurité HTTP (CSP, HSTS, etc.)  │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Couche 4 : Authentification JWT RS256       │
│  • Tokens de courte durée (30 min)          │
│  • RBAC à 5 niveaux                         │
│  • Révocation via JTI                       │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Couche 5 : NetworkPolicy Kubernetes        │
│  • Micro-segmentation inter-pods            │
│  • Egress restreint (DB, Redis, Azure svc)  │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Couche 6 : Sécurité conteneur              │
│  • Image non-root (UID 1001)                │
│  • readOnlyRootFilesystem                   │
│  • Drop ALL capabilities                    │
│  • Seccomp RuntimeDefault                   │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│  Couche 7 : Chiffrement données au repos     │
│  • PostgreSQL : TDE + Customer Managed Key  │
│  • Redis : SSL + AOF persistence            │
│  • Azure Key Vault HSM Premium              │
└─────────────────────────────────────────────┘
```

### 3.2 Matrice des flux autorisés

| Source              | Destination        | Port  | Proto | Autorisé |
|--------------------|--------------------|-------|-------|----------|
| Internet           | WAF/App Gateway    | 443   | HTTPS | ✅ Oui   |
| Internet           | WAF/App Gateway    | 80    | HTTP  | ❌ Non   |
| App Gateway        | AKS (pods)         | 8000  | HTTP  | ✅ Oui   |
| Pods CRM           | PostgreSQL         | 5432  | TCP   | ✅ Oui   |
| Pods CRM           | Redis              | 6380  | TLS   | ✅ Oui   |
| Pods CRM           | Azure Key Vault    | 443   | HTTPS | ✅ Oui   |
| Pods CRM           | Internet           | *     | *     | ❌ Non   |
| Dev/Ops            | AKS (kubectl)      | 443   | HTTPS | ✅ Via Bastion |

---

## 4. GESTION DES IDENTITÉS ET DES ACCÈS

### 4.1 Authentification

**JWT RS256 asymétrique** : contrairement à HMAC (HS256), RS256 permet de valider les tokens sans partager la clé secrète entre services.

- Durée de vie : 30 minutes (access token), 7 jours (refresh token)
- Stockage de la clé privée : Azure Key Vault HSM Premium
- Rotation automatique : tous les 90 jours via Key Vault
- Révocation : possible via le champ `jti` (JWT ID unique) – liste noire Redis

**Hachage des mots de passe** : Argon2id (vainqueur PHC 2015), paramètres :
- Mémoire : 64 MB
- Itérations : 3
- Parallélisme : 4

### 4.2 Contrôle d'accès (RBAC)

| Rôle          | Permissions                                              | Cas d'usage                  |
|--------------|----------------------------------------------------------|------------------------------|
| `admin`       | `*` (tout)                                               | DSI AGROCAM                  |
| `manager`     | read:all, write:commandes, write:clients, read:reports   | Directeur restaurant         |
| `caissier`    | read:menu, write:commandes, read:clients                 | Personnel de caisse          |
| `livreur`     | read:commandes:assigned, write:commandes:status          | Agent livraison              |
| `client_app`  | read:menu, write:commandes:own, read:fidelite:own        | Application mobile client    |

**Principe du moindre privilège** : chaque rôle n'a accès qu'aux ressources strictement nécessaires.

### 4.3 Authentification des services (workload identity)

Les pods AKS s'authentifient auprès d'Azure Key Vault via **Azure Workload Identity** (OIDC) :
- Aucun secret statique dans les variables d'environnement
- Les credentials sont injectés à l'exécution via le CSI Secret Store Driver
- Rotation automatique des secrets montés sans redémarrage du pod

---

## 5. PROTECTION DES DONNÉES

### 5.1 Chiffrement en transit

| Liaison                          | Protocole       | Certificat        |
|---------------------------------|-----------------|-------------------|
| Client → Application Gateway    | TLS 1.3         | Azure Key Vault   |
| Application Gateway → AKS       | HTTP interne    | VNet privé        |
| Pods → PostgreSQL               | TLS 1.2 min     | Azure géré        |
| Pods → Redis                    | TLS 1.2 (6380)  | Azure géré        |
| Pods → Key Vault                | TLS 1.3         | Azure CA          |

### 5.2 Chiffrement au repos

| Composant           | Méthode                          | Clé gérée par        |
|--------------------|----------------------------------|----------------------|
| PostgreSQL Flexible | Azure Storage Encryption (AES-256) | Customer Managed Key |
| Redis Premium       | Chiffrement Azure natif          | Azure géré           |
| Logs d'audit AWS    | SSE-KMS (AES-256)               | Customer Managed Key |
| Secrets             | Azure Key Vault HSM Premium      | Module HSM dédié     |
| Images Docker ACR   | Chiffrement registre             | Azure géré           |

### 5.3 Données personnelles (conformité 2010/012)

- **Minimisation** : seuls les champs nécessaires au service sont collectés
- **Consentement** : champ `consentement_marketing` + `consentement_date` en base
- **Droit à l'oubli** : suppression logique (`is_active=false`) avec anonymisation planifiée à J+365
- **Portabilité** : endpoint dédié `/api/v1/clients/{id}/export` (prévu sprint 3)

---

## 6. SÉCURITÉ DU CODE ET DE LA CHAÎNE CI/CD

### 6.1 Analyse statique (SAST)

Outils intégrés dans la pipeline CI (`.github/workflows/ci.yml`) :

| Outil       | Type d'analyse                    | Seuil de blocage          |
|------------|-----------------------------------|---------------------------|
| **Bandit**  | Vulnérabilités Python             | Niveau MEDIUM ou supérieur |
| **Semgrep** | Patterns OWASP Top 10, JWT, injections | Toute correspondance  |
| **Trivy**   | CVE dans les dépendances Python   | CRITICAL et HIGH           |
| **Trivy**   | CVE dans l'image Docker           | CRITICAL et HIGH (non corrigées) |
| **Checkov** | Mauvaises configurations IaC      | Toute règle Azure/AWS      |

### 6.2 SBOM (Software Bill of Materials)

Chaque image Docker produite en CI embarque une attestation SBOM signée (format SPDX) via `docker buildx` avec `--sbom=true` et `--provenance=true`. Cela permet de :
- Tracer l'origine de chaque dépendance
- Réagir rapidement lors d'une CVE affectant une librairie transitive
- Satisfaire les exigences d'audit de certains clients institutionnels

### 6.3 Sécurité de la chaîne CD

- **OIDC sans credentials** : le déploiement Azure s'authentifie via OIDC (Workload Identity Federation), aucun secret Azure stocké dans GitHub
- **Environnements avec approbation** : le déploiement en production nécessite l'approbation manuelle d'un responsable technique
- **Rollback automatique** : en cas d'échec des vérifications post-déploiement, le pipeline revient automatiquement à la version précédente
- **Séparation staging/prod** : deux environnements GitHub distincts avec des règles de protection différentes

### 6.4 Sécurité des images Docker

- **Image de base** : `python:3.12-slim` (surface d'attaque réduite vs `python:3.12`)
- **Build multi-stage** : les outils de compilation (gcc, libpq-dev) n'apparaissent pas dans l'image finale
- **Utilisateur non-root** : UID 1001 dans le Dockerfile et confirmé par `runAsNonRoot: true` dans le manifest AKS
- **Filesystem en lecture seule** : `readOnlyRootFilesystem: true`
- **No new privileges** : `allowPrivilegeEscalation: false`
- **Capabilities** : `drop: ["ALL"]` – aucune capability Linux conservée

---

## 7. MONITORING ET DÉTECTION DES MENACES

### 7.1 Journalisation centralisée

```
CRM API (JSON structuré)
        │
        ▼
Azure Monitor / Log Analytics (Workspace digitrans-cm-prod-law)
        │
        ├── Alertes en temps réel (KQL queries)
        ├── Tableaux de bord Grafana
        └── Archivage 90 jours en ligne / 2 ans en cold storage

AWS CloudTrail
        │
        ▼
S3 (chiffré KMS) – rétention 7 ans (conformité réglementaire)
```

### 7.2 Détection automatisée

| Système                          | Ce qu'il détecte                                 |
|---------------------------------|--------------------------------------------------|
| **Microsoft Defender for Cloud** | Configurations AKS à risque, secrets exposés     |
| **Defender for Key Vault**       | Accès anormaux aux secrets                       |
| **Defender for Storage**         | Upload de malware, accès depuis IP inconnue       |
| **AWS GuardDuty**                | Menaces sur EKS/S3, comportements anormaux IAM   |
| **AuditMiddleware**              | Toutes les écritures API + erreurs 4xx/5xx       |
| **Rate Limit Middleware**        | Tentatives de brute force / DDoS                 |
| **WAF Azure**                    | Injections SQL, XSS, attaques Web OWASP Top 10  |

### 7.3 Alertes configurées (Azure Monitor)

| Alerte                              | Seuil             | Canal              |
|------------------------------------|-------------------|--------------------|
| Taux d'erreur 5xx > 5%             | 5 min consécutives | PagerDuty + Slack  |
| Latence P99 > 2s                   | 3 min              | Slack              |
| Tentatives login échouées > 20/min | Immédiat           | Slack + Email RSSI |
| Secret Key Vault accédé hors horaires | Immédiat       | Email RSSI + DG    |
| Pod crashloopbackoff               | 3 redémarrages     | Slack              |
| Espace disque PostgreSQL > 80%     | Immédiat           | Slack              |

---

## 8. RÉSILIENCE ET CONTINUITÉ (SPÉCIFIQUE CONTEXTE CAMEROUNAIS)

### 8.1 Mécanisme offline-first

Les délestages de 6 à 12h à Douala constituent le risque opérationnel principal. La solution mise en œuvre :

```
Scénario normal (connectivité OK)
    Caisse → API CRM → PostgreSQL ✅

Scénario dégradé (coupure réseau/électricité)
    Caisse → IndexedDB local (navigateur / application)
           → File d'attente offline (Redis local/mémoire)
           → [Retour connectivité]
           → POST /api/v1/sync/batch (idempotent via offline_sync_id)
           → Replay ordonné des opérations
```

**Garanties** :
- Idempotence : chaque opération offline a un `local_id` unique généré côté client
- Conflits : stratégie "last-write-wins" avec horodatage, les conflits critiques sont marqués pour résolution manuelle
- Durée maximale de stockage offline : 24h (configurable via `REDIS_OFFLINE_QUEUE_TTL`)

### 8.2 Haute disponibilité

| Composant          | Stratégie HA                              | RTO    | RPO    |
|-------------------|-------------------------------------------|--------|--------|
| AKS (CRM pods)    | 3 replicas min + HPA + PDB (2 min dispos) | < 1 min | 0      |
| PostgreSQL Flex    | Zone Redundant (standby zone 2)           | < 1 min | < 30s  |
| Redis Premium      | Persistence AOF + RDB                    | < 5 min | < 1 min |
| Application Gateway | 2 instances (capacity=2)               | Transparente | 0 |
| AWS Aurora BI      | 2 instances + Multi-AZ                  | < 30s  | < 5 min |

---

## 9. GESTION DES INCIDENTS DE SÉCURITÉ

### 9.1 Procédure de réponse

```
Détection (automatique ou manuelle)
    │
    ▼ (< 15 min)
Qualification de l'incident (RSSI CAMTECH)
    │
    ├── Faux positif → Clôture + mise à jour des règles
    └── Incident confirmé
            │
            ▼ (< 1h)
        Containment (isolation pod/service compromis)
            │
            ▼
        Notification AGROCAM (DG + DSI) + CAMTECH Direction
            │
            ▼ (si données personnelles)
        Notification autorités camerounaises (< 72h, loi 2010/012)
            │
            ▼
        Éradication + Remédiation
            │
            ▼
        Retour en production (avec validation sécurité)
            │
            ▼
        Post-mortem (sous 5 jours ouvrés)
```

### 9.2 Contacts d'urgence

| Rôle                     | Contact                                     |
|-------------------------|---------------------------------------------|
| RSSI CAMTECH             | rssi@camtech-solutions.cm / +237 XXX XXX    |
| DSI AGROCAM              | dsi@agrocam.cm / +237 XXX XXX              |
| SOC (astreinte 24/7)     | soc@camtech-solutions.cm                    |
| Microsoft Azure Support  | Ticket P1 via portail Azure                 |
| AWS Support              | Ticket Critical via console AWS             |

---

## 10. ANALYSE DES RISQUES (OWASP Top 10 Web 2021)

| ID    | Risque                                | Impact | Probabilité | Contrôle mis en œuvre                              | Risque résiduel |
|-------|--------------------------------------|--------|-------------|-----------------------------------------------------|-----------------|
| A01   | Broken Access Control                | Élevé  | Moyenne     | RBAC JWT, NetworkPolicy, least privilege            | Faible          |
| A02   | Cryptographic Failures               | Critique | Faible    | TLS 1.3, AES-256, Argon2id, KMS                    | Très faible     |
| A03   | Injection (SQL, etc.)                | Critique | Faible    | ORM SQLAlchemy (paramétré), WAF OWASP 3.2           | Très faible     |
| A04   | Insecure Design                      | Élevé  | Faible      | RBAC, validation Pydantic, schémas stricts          | Faible          |
| A05   | Security Misconfiguration            | Élevé  | Moyenne     | Checkov CI, Defender for Cloud, Seccomp             | Faible          |
| A06   | Vulnerable Components                | Élevé  | Moyenne     | Trivy CI, Dependabot, SBOM                          | Faible          |
| A07   | Auth & Session Failures              | Critique | Faible    | JWT RS256, courte durée, rate limiting, Argon2id    | Très faible     |
| A08   | Software & Data Integrity Failures   | Élevé  | Faible      | Semgrep CI, SBOM signé, Git branch protection      | Faible          |
| A09   | Security Logging & Monitoring Gaps   | Élevé  | Faible      | AuditMiddleware, CloudTrail, Defender, Alertes      | Faible          |
| A10   | SSRF                                 | Moyen  | Faible      | Egress NetworkPolicy restrictif, whitelist URLs     | Faible          |

---

## 11. RECOMMANDATIONS ET PLAN D'ACTION

### Recommandations immédiates (Sprint en cours)

1. **Activer l'authentification multifacteur (MFA)** pour tous les comptes Azure AD ayant accès au Key Vault et à l'AKS → Action : DSI AGROCAM, délai 2 semaines
2. **Configurer le Bastion Azure** pour remplacer les accès SSH directs aux nœuds AKS → Action : DevOps CAMTECH, délai 1 semaine
3. **Tester le scénario offline** sur les caisses des 5 restaurants SavoirManger avec des données réelles (mode recette) → Action : Chef de projet, délai 3 semaines

### Recommandations à 3 mois

4. **Pentest externe** : missionner un cabinet spécialisé pour un test de pénétration de la surface d'attaque exposée (API publique + Application Gateway) avant mise en production officielle
5. **Mise en place du WAF en mode Learning** pendant 30 jours pour affiner les règles sans créer de faux positifs sur les cas d'usage spécifiques AGROCAM
6. **Formation sécurité** des développeurs CAMTECH sur les OWASP Top 10 et les bonnes pratiques FastAPI/JWT

### Recommandations à 6 mois

7. **Intégration blockchain pour l'audit trail** (traçabilité Supply Chain) : évaluer Hyperledger Fabric ou Azure Confidential Ledger pour horodater les lots de marchandises portuaires
8. **Revue DPIA** (Data Protection Impact Assessment) en anticipation d'une éventuelle loi camerounaise sur la protection des données alignée sur le RGPD
9. **Mise en place d'un SIEM** (Security Information and Event Management) consolidant les logs Azure Monitor + AWS CloudWatch pour une vue unifiée des menaces

---

## 12. CONFORMITÉ ET CERTIFICATIONS

| Référentiel              | Statut actuel         | Cible                        |
|--------------------------|----------------------|------------------------------|
| Loi 2010/012 Cameroun    | ✅ Conforme           | Maintien                     |
| ISO 27001                | 🔄 En évaluation      | Certification S2 2027        |
| RGPD / Protection données | ⚠️ Alignement partiel | Conformité complète S1 2027 |
| PCI-DSS (Mobile Money)   | ℹ️ Non applicable     | Si paiements carte intégrés  |

---

## 13. CONCLUSION

L'architecture sécurité déployée dans le cadre du projet DIGITRANS-CM respecte les principes de **défense en profondeur** avec sept couches de contrôles superposées, depuis le WAF Azure jusqu'au chiffrement des données au repos. Elle répond spécifiquement aux contraintes du contexte camerounais :

- **Souveraineté des données** : aucune donnée PII ne quitte le continent africain (Azure Egypt, AWS Afrique du Sud)
- **Résilience aux coupures** : mécanisme offline-first avec synchronisation idempotente permettant de continuer à opérer sans connectivité
- **Conformité légale** : audit trail conforme à la loi 2010/012, rétention 7 ans, notification d'incidents documentée
- **Économie de coûts** : architecture serverless/managed qui évite l'investissement en infrastructure physique

Le risque résiduel est évalué comme **faible** pour l'ensemble des vecteurs d'attaque OWASP Top 10, sous réserve de la mise en œuvre des recommandations listées en section 11, notamment la réalisation du test de pénétration avant mise en production officielle.

---

*Document produit par l'équipe Cybersécurité de CAMTECH SOLUTIONS S.A.*
*Toute reproduction ou diffusion sans autorisation est interdite.*
*© 2026 CAMTECH SOLUTIONS S.A. – Douala, Cameroun*
