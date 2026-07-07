# 🔧 GarageApp — Système de gestion de garage automobile

Application Django complète pour la gestion d'un garage professionnel multi-ateliers.

---

## 🚀 DÉMARRAGE RAPIDE (Docker — Recommandé)

### Prérequis
- Docker Desktop installé
- Docker Compose v2+

### Lancement en 3 commandes

```bash
# 1. Cloner / accéder au projet
git clone https://github.com/dylano-mecbien/garage-tracking.git
cd garage_suivi

# 2. Lancer tous les services
docker-compose up -d --build

# 3. Initialiser la base de données + comptes par défaut
docker-compose exec web python manage.py create_default_admin
```

**L'application est disponible sur : http://localhost**

---

> ⚠️ **Changez ces mots de passe en production !**

---

## 🗺️ INTERFACES PAR RÔLE

Après connexion, chaque rôle est automatiquement redirigé :

| Rôle              | URL Dashboard                    |
|-------------------|----------------------------------|
| Admin             | `/admin-garage/dashboard/`       |
| Guérite           | `/guerite/dashboard/`            |
| Réception         | `/reception/dashboard/`          |
| Resp. Atelier     | `/atelier/dashboard/`            |
| Technicien        | `/atelier/technicien/dashboard/` |

---

## 🛠️ INSTALLATION MANUELLE (sans Docker)

### 1. Créer l'environnement Python

```bash
python -m venv venv
source venv/bin/activate          # Linux/Mac
# ou
venv\Scripts\activate             # Windows

pip install -r requirements.txt
```

### 2. Installer et démarrer PostgreSQL

```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib

# Créer la base
sudo -u postgres psql << SQL
CREATE DATABASE garage_db;
CREATE USER garage_user WITH PASSWORD 'garage_password';
GRANT ALL PRIVILEGES ON DATABASE garage_db TO garage_user;
ALTER DATABASE garage_db OWNER TO garage_user;
SQL
```

### 3. Installer et démarrer Redis

```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# Vérifier
redis-cli ping   # → PONG
```

### 4. Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditer .env avec vos valeurs
nano .env
```

### 5. Migrations et données initiales

```bash
python manage.py migrate
python manage.py create_default_admin
python manage.py collectstatic --noinput
```

### 6. Lancer le serveur de développement

```bash
python manage.py runserver
```

**Accès : http://127.0.0.1:8000**

---

## 🐳 COMMANDES DOCKER UTILES

```bash
# Démarrer tous les services
docker-compose up -d

# Voir les logs
docker-compose logs -f web
 
# Accéder au shell Django
docker-compose exec web python manage.py shell

# Créer un superutilisateur custom
docker-compose exec web python manage.py createsuperuser

# Appliquer les migrations
docker-compose exec web python manage.py migrate

# Arrêter tous les services
docker-compose down

# Arrêter et supprimer les volumes (RESET COMPLET)
docker-compose down -v
psql -h localhost -p 5432 -U garage_user -d garage_db
\dt


# autre
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
sudo systemctl stop postgresql
sudo find . -path "*/migrations/*.py" -not -name "__init__.py" -delete


```

---

## 🌐 SERVICES ET PORTS

| Service      | URL                          | Description              |
|-------------|----------     ---------------------|--------------------------|
| Application | http://localhost         | Interface principale     |
| API REST    | http://localhost/api/v1/      | API REST                 |
| Swagger     | http://localhost/api/docs/    | Documentation API        |
| MinIO       | http://localhost:9001         | Stockage fichiers (UI)   |
| PostgreSQL  | localhost:5432                | Base de données          |
| Redis       | localhost:6379                | Cache / Sessions         |

---

## 📋 FLUX MÉTIER

### Cas 1 : Véhicule en visite
```
Guérite → Entrée (motif: VISITE) → Travaux → Sortie directe
```

### Cas 2 : Véhicule en réparation
```
Guérite → Entrée (motif: RÉPARATION)
→ Réception → Créer réception → Devis → Transférer atelier
→ Atelier (Resp.) → Créer OR → Fiche contrôle → Fiche technique → Tâches
→ Techniciens → Démarrer tâche → Compte rendu → Terminer tâche
→ Atelier (Resp.) → Clôturer OR
→ Réception → Bon de sortie
→ Guérite → Vérifier bon → Enregistrer sortie
```

### Cas 3 : Retour malfaçon
```
Guérite → Nouvelle entrée
→ Réception → Nouvelle réception
→ Atelier → Créer OR RETOUR (depuis OR clôturé)
   → Copie automatique fiche technique + sélection tâches
→ Suite identique au cas 2
```

---

## 📁 STRUCTURE DU PROJET

```
garage_suivi/
├── garage/
│   ├── settings/         # Configuration Django
│   ├── urls.py           # URLs principales
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── accounts/         # Utilisateurs & Rôles
│   ├── vehicules/        # Véhicules, Clients, Conducteurs
│   ├── guerite/          # Entrées & Sorties
│   ├── reception/        # Réceptions, Devis, Factures
│   ├── atelier/          # OR, Tâches, Fiches techniques
│   ├── documents/        # Génération PDF
│   └── audit/            # Logs d'audit
├── templates/            # Templates HTML
│   ├── base.html
│   ├── accounts/         # Connexion, profil
│   ├── admin_custom/     # Interface Admin
│   ├── guerite/          # Interface Guérite
│   ├── reception/        # Interface Réception
│   ├── atelier/
│   │   ├── resp/         # Interface Responsable Atelier
│   │   └── technicien/   # Interface Technicien
│   └── vehicules/
├── static/               # CSS, JS, images
├── media/                # Fichiers uploadés
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env
```

---

## 🔒 SÉCURITÉ

- ✅ JWT Authentication (API REST)
- ✅ Session Authentication (interface web)
- ✅ RBAC — Rôles stricts par interface
- ✅ Anti brute-force (verrouillage 15 min après 5 échecs)
- ✅ Logs d'audit complets (connexions, modifications, exports)
- ✅ Rate limiting via Redis
- ✅ CSRF protection
- ✅ IP logging

---

## 📊 API REST

```bash
# Obtenir un token JWT
curl -X POST http://localhost/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@garage.cm","password":"Admin@2026"}'

# Utiliser le token
curl http://localhost/api/v1/vehicules/vehicules/ \
  -H "Authorization: Bearer <access_token>"
```

Endpoints disponibles :
- `/api/v1/vehicules/` — Véhicules, Clients, Conducteurs
- `/api/v1/guerite/` — Entrées, Bons de sortie
- `/api/v1/reception/` — Réceptions, Devis, Factures
- `/api/v1/atelier/` — OR, Tâches, Ateliers
- `/api/docs/` — Swagger UI

---

## ⚡ EN CAS DE PROBLÈME

```bash
# Voir les logs d'erreur
docker-compose logs web --tail=50

# Réinitialiser la base (ATTENTION: perte de données)
docker-compose down -v
docker-compose up -d --build
docker-compose exec web python manage.py create_default_admin

# Problème de permissions fichiers
chmod +x manage.py

# Vérifier que PostgreSQL est prêt
docker-compose exec db pg_isready -U garage_user
```
