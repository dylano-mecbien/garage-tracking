# 🔧 Garage Suivi — Système de gestion de garage automobile

Application Django complète pour la gestion d'un garage professionnel multi-ateliers.

---

## 🚀 DÉMARRAGE RAPIDE (Docker — Recommandé)

### Prérequis
- Docker Desktop installé
- Docker Compose v2+
- `make` installé (inclus sur Linux/Mac — Windows : installer [WSL2](https://learn.microsoft.com/fr-fr/windows/wsl/install) ou [GNU Make](https://gnuwin32.sourceforge.net/packages/make.htm))

### Lancement en 3 commandes

```bash
# 1. Cloner le projet
git clone https://github.com/dylano-mecbien/garage-tracking.git
cd garage_suivi

# 2. Lancer tous les services
make dev-build

# 3. Initialiser la base de données + comptes par défaut
make seed
```

**L'application est disponible sur : http://localhost**

> ⚠️ **Changez les mots de passe en production !**

---

## 📋 TOUTES LES COMMANDES MAKE

```bash
make help   # Afficher toutes les commandes disponibles
```

### 🛠 Développement

```bash
make dev              # Démarrer l'environnement de développement
make dev-build        # Rebuild + démarrer
make stop             # Arrêter les conteneurs
make restart          # Redémarrer les conteneurs
make logs             # Voir les logs en temps réel
make logs-all         # Logs de tous les services
make shell            # Ouvrir un shell dans le conteneur web
make status           # État des conteneurs
make manage cmd=shell # Exécuter python manage.py <cmd>
```

### 🗄 Base de données

```bash
make migrate                      # Appliquer les migrations
make makemigrations               # Créer les migrations
make makemigrations-app app=guerite  # Migrations pour une app spécifique
make seed                         # Charger les données de démo
make superuser                    # Créer un superutilisateur
make dbshell                      # Ouvrir le shell PostgreSQL
make reset-db                     # ⚠️ Réinitialiser complètement la base (dev)
make backup-local                 # Sauvegarder la base locale
```

### 📦 Statiques

```bash
make static           # Collecter les fichiers statiques
```

### 🚀 Production

```bash
make prod-up          # Démarrer la production (build inclus)
make prod-stop        # Arrêter la production
make prod-restart     # Redémarrer la production
make prod-logs        # Logs prod en temps réel
make prod-logs-nginx  # Logs Nginx uniquement
make prod-status      # État de tous les conteneurs prod
make prod-deploy      # Déployer une nouvelle version (git pull + rebuild + migrate)
make prod-shell       # Shell dans le conteneur web prod
make prod-migrate     # Appliquer les migrations en prod
make prod-static      # Collecter les statiques en prod
make prod-superuser   # Créer un superutilisateur en prod
make prod-manage cmd=check  # Exécuter manage.py en prod
```

### 💾 Sauvegardes

```bash
make backup                               # Créer une sauvegarde prod
make backup-list                          # Lister les sauvegardes disponibles
make restore file=backups/backup_XXX.dump # Restaurer une sauvegarde
```

### 🔐 SSL / HTTPS

```bash
make ssl-init domain=garage.votredomaine.com  # Obtenir le certificat (1ère fois)
make ssl-renew                                # Renouveler le certificat
make ssl-status                               # Vérifier l'état du certificat
```

### 🧹 Nettoyage & utilitaires

```bash
make clean            # Arrêter et supprimer les conteneurs dev
make clean-all        # ⚠️ Tout supprimer (conteneurs + volumes + images)
make prune            # Nettoyer les images Docker inutilisées
make check            # Vérification système Django (dev)
make check-prod       # Vérification Django deploy checklist (prod)
make test             # Lancer les tests
make secret-key       # Générer une nouvelle SECRET_KEY
make env-check        # Afficher les variables d'environnement chargées
```

---

## 🗺️ INTERFACES PAR RÔLE

Après connexion, chaque rôle est automatiquement redirigé :

| Rôle              | URL Dashboard                      | Compte démo                         |
|-------------------|------------------------------------|-------------------------------------|
| Admin             | `/admin-garage/dashboard/`         | `admin@garage.cm / Garage@Admin2024`|
| Guérite           | `/guerite/dashboard/`              | `guerite1@garage.cm / Garage@2024`  |
| Réception         | `/reception/dashboard/`            | `reception1@garage.cm / Garage@2024`|
| Resp. Atelier     | `/atelier/dashboard/`              | `resp.atelier1@garage.cm / Garage@2024` |
| Technicien        | `/atelier/technicien/dashboard/`   | `tech1@garage.cm / Garage@2024`     |

---

## 🛠️ INSTALLATION MANUELLE (sans Docker)

### 1. Créer l'environnement Python

```bash
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 2. Installer PostgreSQL et Redis

```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib redis-server

# Créer la base
sudo -u postgres psql << SQL
CREATE DATABASE garage_db;
CREATE USER garage_user WITH PASSWORD 'garage_password';
GRANT ALL PRIVILEGES ON DATABASE garage_db TO garage_user;
ALTER DATABASE garage_db OWNER TO garage_user;
SQL

# Démarrer Redis
sudo systemctl start redis
redis-cli ping   # → PONG
```

### 3. Configurer les variables d'environnement

```bash
cp .env.example .env
nano .env   # Remplir avec vos valeurs
```

### 4. Migrations et démarrage

```bash
python manage.py migrate
python manage.py create_default_admin
python manage.py collectstatic --noinput
python manage.py runserver
```

**Accès : http://127.0.0.1:8000**

---

## 🌐 SERVICES ET PORTS

| Service      | URL                           | Description              |
|--------------|-------------------------------|--------------------------|
| Application  | http://localhost               | Interface principale     |
| API REST     | http://localhost/api/v1/       | API REST                 |
| Swagger      | http://localhost/api/docs/     | Documentation API        |
| PostgreSQL   | localhost:5432                 | Base de données          |
| Redis        | localhost:6379                 | Cache / Sessions         |

---

## 📋 FLUX MÉTIER

### Flux 1 — Sortie directe (sans réparation)
```
Guérite → Entrée (motif: RÉPARATION)
→ Réception → Créer réception → Rapport (décision: SORTIE DIRECTE)
→ Réception → Bon de sortie
→ Guérite → Vérifier bon → Enregistrer sortie
```

### Flux 2 — Réparation complète (avec fiche technique)
```
Guérite → Entrée (motif: RÉPARATION)
→ Réception → Créer réception → Rapport → Transfert atelier(s)
→ Atelier (Resp.) → Fiche de contrôle  [véhicule passe à PRÉSENT ATELIER]
→ Atelier (Resp.) → Créer OR → Fiche technique → Tâches
→ Techniciens → Démarrer tâche → Compte rendu → Terminer tâche
→ Atelier (Resp.) → Clôturer OR  [notification réception]
→ Réception → Bon de sortie  [email envoyé au valideur]
→ Guérite → Vérifier bon → Signature → Enregistrer sortie
```

### Flux 3 — Réparation directe (sans fiche technique)
```
Guérite → Entrée
→ Réception → Rapport → Transfert atelier
→ Atelier → Fiche de contrôle → Réparation directe
→ Clôturer OR → Bon de sortie → Sortie
```

### Flux 4 — Retour malfaçon
```
Guérite → Nouvelle entrée
→ Réception → Nouvelle réception
→ Atelier → Créer OR RETOUR (depuis OR clôturé)
   → Copie automatique fiche technique + sélection tâches
→ Suite identique au flux 2
```

---

## 📁 STRUCTURE DU PROJET

```
garage_suivi/
├── Makefile                  # ← Toutes les commandes dev & prod
├── docker-compose.yml        # Dev
├── docker-compose.prod.yml   # Production
├── Dockerfile
├── Dockerfile.prod
├── requirements.txt
├── .env                      # Variables d'environnement (ne pas commiter)
├── .env.production.example   # Modèle pour la prod
│
├── garage/
│   ├── settings/
│   │   ├── base.py
│   │   └── production.py
│   └── urls.py
│
├── apps/
│   ├── accounts/             # Utilisateurs & Rôles
│   ├── vehicules/            # Véhicules, Clients, Conducteurs
│   ├── guerite/              # Entrées, Sorties, Bons de sortie
│   ├── reception/            # Réceptions, Rapports, Transferts
│   ├── atelier/              # OR, Tâches, Fiches contrôle/technique
│   ├── notifications/        # Destinataires email, service envoi
│   ├── documents/            # Génération PDF
│   └── audit/                # Logs d'audit complets
│
├── templates/
│   ├── base.html
│   ├── accounts/
│   ├── admin_custom/
│   │   ├── dashboard.html
│   │   ├── audit_logs.html
│   │   ├── destinataires_email.html
│   │   └── utilisateurs/
│   ├── guerite/
│   │   ├── entree/
│   │   └── bon_sortie/
│   ├── reception/
│   └── atelier/
│       ├── resp/
│       └── technicien/
│
├── static/
├── media/
├── backups/                  # Sauvegardes DB (généré automatiquement)
└── nginx/
    ├── nginx.conf            # Dev
    └── nginx.prod.conf       # Production
```

---

## 📧 NOTIFICATIONS EMAIL

Lors de la création d'un bon de sortie, un email est automatiquement envoyé
aux destinataires configurés dans **Admin → Destinataires email**.

Configuration dans `.env` :
```bash
EMAIL_HOST=smtp-relay.brevo.com   # Brevo recommandé en prod
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=votre@email.com
EMAIL_HOST_PASSWORD=votre-cle-api
DEFAULT_FROM_EMAIL=garage@votredomaine.com
```

> Pour Gmail : utilisez un **mot de passe d'application** (myaccount.google.com/apppasswords)

---

## 🔒 SÉCURITÉ

- ✅ Authentification par session (web) + JWT (API REST)
- ✅ RBAC — Rôles stricts par interface (Admin, Guérite, Réception, Atelier, Technicien)
- ✅ Anti brute-force (verrouillage 15 min après 5 échecs)
- ✅ Logs d'audit complets (connexions, créations, modifications, exports)
- ✅ Rate limiting Nginx sur la page de connexion
- ✅ CSRF protection + cookies sécurisés
- ✅ HTTPS obligatoire en production (HSTS activé)
- ✅ Utilisateur Docker non-root en production
- ✅ IP logging sur toutes les connexions

---

## 📊 API REST

```bash
# Obtenir un token JWT
curl -X POST http://localhost/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@garage.cm","password":"Garage@Admin2024"}'

# Utiliser le token
curl http://localhost/api/v1/vehicules/ \
  -H "Authorization: Bearer <access_token>"
```

Endpoints :
- `/api/v1/vehicules/` — Véhicules, Clients, Conducteurs
- `/api/v1/guerite/` — Entrées, Bons de sortie
- `/api/v1/reception/` — Réceptions, Rapports
- `/api/v1/atelier/` — OR, Tâches, Ateliers
- `/api/docs/` — Swagger UI

---

## ⚡ DÉPANNAGE RAPIDE

```bash
# Voir les logs d'erreur
make logs

# Réinitialiser complètement la base (⚠️ perte de données)
make reset-db

# Vérifier que PostgreSQL est prêt
make manage cmd="dbshell"

# Vérifier la configuration Django
make check

# Supprimer toutes les migrations et les recréer
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
make makemigrations
make migrate

# Problème SSL en production
make ssl-status
make ssl-renew


sudo systemctl stop postgresql
# Voir les logs Nginx en prod
make prod-logs-nginx
```

