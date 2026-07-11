# ════════════════════════════════════════════════════════════════════
#  Garage Suivi — Makefile
#  Usage : make <commande>
#  Dev   : make dev, make logs, make shell...
#  Prod  : make prod-up, make prod-logs, make backup...
# ════════════════════════════════════════════════════════════════════

# ─── Configuration ───────────────────────────────────────────────────────────
DC      = docker compose
DC_PROD = docker compose -f docker-compose.prod.yml
APP     = web
DB      = db

.DEFAULT_GOAL := help

# ─── Couleurs terminal ────────────────────────────────────────────────────────
CYAN  = \033[0;36m
GREEN = \033[0;32m
YELLOW= \033[0;33m
RED   = \033[0;31m
RESET = \033[0m
BOLD  = \033[1m

# ════════════════════════════════════════════════════════════════════
#  AIDE
# ════════════════════════════════════════════════════════════════════

help:
	@echo ""
	@echo "$(BOLD)$(CYAN) ╔══════════════════════════════════════╗$(RESET)"
	@echo "$(BOLD)$(CYAN) ║       Garage Suivi — Makefile        ║$(RESET)"
	@echo "$(BOLD)$(CYAN) ╚══════════════════════════════════════╝$(RESET)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 🛠  DÉVELOPPEMENT$(RESET)"
	@echo "   $(CYAN)make dev$(RESET)             Démarrer l'environnement de développement"
	@echo "   $(CYAN)make dev-build$(RESET)       Rebuild + démarrer en dev"
	@echo "   $(CYAN)make stop$(RESET)            Arrêter les conteneurs dev"
	@echo "   $(CYAN)make restart$(RESET)         Redémarrer les conteneurs dev"
	@echo "   $(CYAN)make logs$(RESET)            Voir les logs dev en temps réel"
	@echo "   $(CYAN)make shell$(RESET)           Ouvrir un shell dans le conteneur web"
	@echo "   $(CYAN)make manage cmd=...$(RESET)  Exécuter manage.py (ex: make manage cmd=createsuperuser)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 🗄  BASE DE DONNÉES$(RESET)"
	@echo "   $(CYAN)make migrate$(RESET)         Appliquer les migrations"
	@echo "   $(CYAN)make makemigrations$(RESET)  Créer les migrations"
	@echo "   $(CYAN)make seed$(RESET)            Charger les données de démo (create_default_admin)"
	@echo "   $(CYAN)make dbshell$(RESET)         Ouvrir le shell PostgreSQL"
	@echo "   $(CYAN)make reset-db$(RESET)        ⚠️  Supprimer et recréer la base (dev uniquement)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 📦 STATIQUES & ASSETS$(RESET)"
	@echo "   $(CYAN)make static$(RESET)          Collecter les fichiers statiques"
	@echo ""
	@echo "$(BOLD)$(RED) 🚀 PRODUCTION$(RESET)"
	@echo "   $(CYAN)make prod-up$(RESET)         Démarrer la production (build inclus)"
	@echo "   $(CYAN)make prod-stop$(RESET)       Arrêter la production"
	@echo "   $(CYAN)make prod-restart$(RESET)    Redémarrer la production"
	@echo "   $(CYAN)make prod-logs$(RESET)       Voir les logs prod en temps réel"
	@echo "   $(CYAN)make prod-status$(RESET)     Voir l'état des conteneurs prod"
	@echo "   $(CYAN)make prod-deploy$(RESET)     Déployer une nouvelle version (pull + rebuild)"
	@echo "   $(CYAN)make prod-shell$(RESET)      Shell dans le conteneur web prod"
	@echo "   $(CYAN)make prod-migrate$(RESET)    Migrer en production"
	@echo ""
	@echo "$(BOLD)$(GREEN) 💾 SAUVEGARDES$(RESET)"
	@echo "   $(CYAN)make backup$(RESET)          Créer une sauvegarde de la base"
	@echo "   $(CYAN)make backup-list$(RESET)     Lister les sauvegardes disponibles"
	@echo "   $(CYAN)make restore file=...$(RESET) Restaurer une sauvegarde (ex: make restore file=backup_20250601.dump)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 🔐 SSL$(RESET)"
	@echo "   $(CYAN)make ssl-init domain=...$(RESET)  Obtenir le certificat SSL (1ère fois)"
	@echo "   $(CYAN)make ssl-renew$(RESET)            Renouveler le certificat SSL"
	@echo ""
	@echo "$(BOLD)$(GREEN) 🧹 NETTOYAGE$(RESET)"
	@echo "   $(CYAN)make clean$(RESET)           Arrêter et supprimer les conteneurs dev"
	@echo "   $(CYAN)make clean-all$(RESET)       ⚠️  Tout supprimer (conteneurs + volumes + images)"
	@echo "   $(CYAN)make prune$(RESET)           Nettoyer les images Docker inutilisées"
	@echo ""

# ════════════════════════════════════════════════════════════════════
#  DÉVELOPPEMENT
# ════════════════════════════════════════════════════════════════════

dev:
	@echo "$(GREEN)▶ Démarrage de l'environnement de développement...$(RESET)"
	$(DC) up -d
	@echo "$(GREEN)✅ Disponible sur http://localhost$(RESET)"

dev-build:
	@echo "$(GREEN)▶ Build + démarrage dev...$(RESET)"
	$(DC) up -d --build
	@echo "$(GREEN)✅ Disponible sur http://localhost$(RESET)"

stop:
	@echo "$(YELLOW)⏹ Arrêt des conteneurs dev...$(RESET)"
	$(DC) stop

restart:
	@echo "$(YELLOW)🔄 Redémarrage des conteneurs dev...$(RESET)"
	$(DC) restart

logs:
	$(DC) logs -f $(APP)

logs-all:
	$(DC) logs -f

shell:
	@echo "$(CYAN)🐚 Ouverture du shell dans le conteneur web...$(RESET)"
	$(DC) exec $(APP) bash

manage:
	@echo "$(CYAN)⚙️  Exécution: python manage.py $(cmd)$(RESET)"
	$(DC) exec $(APP) python manage.py $(cmd)

status:
	$(DC) ps

# ════════════════════════════════════════════════════════════════════
#  BASE DE DONNÉES
# ════════════════════════════════════════════════════════════════════

migrate:
	@echo "$(CYAN)🗄  Migration de la base de données...$(RESET)"
	$(DC) exec $(APP) python manage.py migrate
	@echo "$(GREEN)✅ Migrations appliquées$(RESET)"

makemigrations:
	@echo "$(CYAN)🗄  Création des migrations...$(RESET)"
	$(DC) exec $(APP) python manage.py makemigrations

makemigrations-app:
	@echo "$(CYAN)🗄  Création des migrations pour $(app)...$(RESET)"
	$(DC) exec $(APP) python manage.py makemigrations $(app)

seed:
	@echo "$(CYAN)🌱 Chargement des données de démo...$(RESET)"
	$(DC) exec $(APP) python manage.py create_default_admin
	@echo "$(GREEN)✅ Données de démo chargées$(RESET)"

superuser:
	@echo "$(CYAN)👤 Création d'un super-utilisateur...$(RESET)"
	$(DC) exec $(APP) python manage.py createsuperuser

dbshell:
	@echo "$(CYAN)🗄  Ouverture du shell PostgreSQL...$(RESET)"
	$(DC) exec $(DB) psql -U $${DB_USER:-garage_user} -d $${DB_NAME:-garage_db}

reset-db:
	@echo "$(RED)⚠️  ATTENTION: Cette commande supprime TOUTES les données !$(RESET)"
	@read -p "Confirmer ? (oui/non) : " confirm && [ "$$confirm" = "oui" ] || exit 1
	$(DC) down -v
	$(DC) up -d $(DB)
	@echo "$(YELLOW)⏳ Attente démarrage PostgreSQL...$(RESET)"
	@sleep 5
	$(DC) up -d $(APP)
	@sleep 3
	$(MAKE) migrate
	$(MAKE) seed
	@echo "$(GREEN)✅ Base réinitialisée avec données de démo$(RESET)"

# ════════════════════════════════════════════════════════════════════
#  STATIQUES
# ════════════════════════════════════════════════════════════════════

static:
	@echo "$(CYAN)📦 Collecte des fichiers statiques...$(RESET)"
	$(DC) exec $(APP) python manage.py collectstatic --noinput
	@echo "$(GREEN)✅ Fichiers statiques collectés$(RESET)"

# ════════════════════════════════════════════════════════════════════
#  PRODUCTION
# ════════════════════════════════════════════════════════════════════

prod-up:
	@echo "$(GREEN)🚀 Démarrage de la production...$(RESET)"
	$(DC_PROD) up -d --build
	@echo "$(GREEN)✅ Application en production démarrée$(RESET)"

prod-stop:
	@echo "$(YELLOW)⏹ Arrêt de la production...$(RESET)"
	$(DC_PROD) stop

prod-restart:
	@echo "$(YELLOW)🔄 Redémarrage de la production...$(RESET)"
	$(DC_PROD) restart

prod-logs:
	$(DC_PROD) logs -f $(APP)

prod-logs-all:
	$(DC_PROD) logs -f

prod-logs-nginx:
	$(DC_PROD) logs -f nginx

prod-status:
	@echo "$(CYAN)📊 État des conteneurs production :$(RESET)"
	$(DC_PROD) ps

prod-shell:
	@echo "$(CYAN)🐚 Ouverture du shell prod...$(RESET)"
	$(DC_PROD) exec $(APP) bash

prod-manage:
	$(DC_PROD) exec $(APP) python manage.py $(cmd)

prod-migrate:
	@echo "$(CYAN)🗄  Migration en production...$(RESET)"
	$(DC_PROD) exec $(APP) python manage.py migrate --noinput
	@echo "$(GREEN)✅ Migrations prod appliquées$(RESET)"

prod-static:
	@echo "$(CYAN)📦 Collecte statiques prod...$(RESET)"
	$(DC_PROD) exec $(APP) python manage.py collectstatic --noinput

prod-deploy:
	@echo "$(GREEN)🚀 Déploiement nouvelle version...$(RESET)"
	git pull
	$(DC_PROD) up -d --build $(APP)
	$(MAKE) prod-migrate
	$(MAKE) prod-static
	@echo "$(GREEN)✅ Déploiement terminé$(RESET)"

prod-superuser:
	$(DC_PROD) exec $(APP) python manage.py createsuperuser

# ════════════════════════════════════════════════════════════════════
#  SAUVEGARDES
# ════════════════════════════════════════════════════════════════════

backup:
	@echo "$(CYAN)💾 Sauvegarde de la base de données...$(RESET)"
	@mkdir -p backups
	$(DC_PROD) exec -T $(DB) pg_dump \
		-U $${DB_USER:-garage_db_prod} \
		$${DB_NAME:-garage_db_prod} \
		-F c \
		> backups/backup_$$(date +%Y%m%d_%H%M%S).dump
	@echo "$(GREEN)✅ Sauvegarde créée dans ./backups/$(RESET)"
	@ls -lh backups/*.dump | tail -1

backup-local:
	@echo "$(CYAN)💾 Sauvegarde locale (dev)...$(RESET)"
	@mkdir -p backups
	$(DC) exec -T $(DB) pg_dump \
		-U $${DB_USER:-garage_user} \
		$${DB_NAME:-garage_db} \
		-F c \
		> backups/backup_local_$$(date +%Y%m%d_%H%M%S).dump
	@echo "$(GREEN)✅ Sauvegarde locale créée$(RESET)"
	@ls -lh backups/*.dump | tail -1

backup-list:
	@echo "$(CYAN)📋 Sauvegardes disponibles :$(RESET)"
	@ls -lh backups/*.dump 2>/dev/null || echo "  Aucune sauvegarde trouvée dans ./backups/"

restore:
	@echo "$(RED)⚠️  Restauration de : $(file)$(RESET)"
	@[ -n "$(file)" ] || (echo "$(RED)❌ Précisez le fichier : make restore file=backups/backup_XXX.dump$(RESET)" && exit 1)
	@[ -f "$(file)" ] || (echo "$(RED)❌ Fichier introuvable : $(file)$(RESET)" && exit 1)
	@read -p "Confirmer la restauration ? (oui/non) : " confirm && [ "$$confirm" = "oui" ] || exit 1
	$(DC_PROD) exec -T $(DB) pg_restore \
		-U $${DB_USER:-garage_db_prod} \
		-d $${DB_NAME:-garage_db_prod} \
		-c --if-exists \
		< $(file)
	@echo "$(GREEN)✅ Restauration terminée$(RESET)"

# ════════════════════════════════════════════════════════════════════
#  SSL / CERTBOT
# ════════════════════════════════════════════════════════════════════

ssl-init:
	@[ -n "$(domain)" ] || (echo "$(RED)❌ Précisez le domaine : make ssl-init domain=garage.votredomaine.com$(RESET)" && exit 1)
	@echo "$(CYAN)🔐 Obtention du certificat SSL pour $(domain)...$(RESET)"
	$(DC_PROD) up -d nginx
	docker run --rm \
		-v $$(pwd)/certbot_certs:/etc/letsencrypt \
		-v $$(pwd)/certbot_www:/var/www/certbot \
		certbot/certbot certonly --webroot \
		-w /var/www/certbot \
		-d $(domain) \
		--email $${ADMIN_EMAIL:-admin@$(domain)} \
		--agree-tos --no-eff-email
	@echo "$(GREEN)✅ Certificat SSL obtenu$(RESET)"
	$(DC_PROD) restart nginx

ssl-renew:
	@echo "$(CYAN)🔄 Renouvellement du certificat SSL...$(RESET)"
	$(DC_PROD) exec certbot certbot renew --quiet
	$(DC_PROD) exec nginx nginx -s reload
	@echo "$(GREEN)✅ SSL renouvelé$(RESET)"

ssl-status:
	$(DC_PROD) exec certbot certbot certificates

# ════════════════════════════════════════════════════════════════════
#  NETTOYAGE
# ════════════════════════════════════════════════════════════════════

clean:
	@echo "$(YELLOW)🧹 Nettoyage des conteneurs dev...$(RESET)"
	$(DC) down

clean-all:
	@echo "$(RED)⚠️  Suppression de TOUT (conteneurs + volumes + images)$(RESET)"
	@read -p "Confirmer ? (oui/non) : " confirm && [ "$$confirm" = "oui" ] || exit 1
	$(DC) down -v --rmi all
	@echo "$(GREEN)✅ Nettoyage complet$(RESET)"

prune:
	@echo "$(YELLOW)🧹 Nettoyage des images Docker inutilisées...$(RESET)"
	docker image prune -f
	docker volume prune -f
	@echo "$(GREEN)✅ Docker nettoyé$(RESET)"

# ════════════════════════════════════════════════════════════════════
#  DIVERS
# ════════════════════════════════════════════════════════════════════

check:
	@echo "$(CYAN)🔍 Vérification du système Django...$(RESET)"
	$(DC) exec $(APP) python manage.py check

check-prod:
	@echo "$(CYAN)🔍 Vérification système Django (prod)...$(RESET)"
	$(DC_PROD) exec $(APP) python manage.py check --deploy

test:
	@echo "$(CYAN)🧪 Lancement des tests...$(RESET)"
	$(DC) exec $(APP) python manage.py test --verbosity=2

secret-key:
	@echo "$(CYAN)🔑 Génération d'une nouvelle SECRET_KEY :$(RESET)"
	@$(DC) exec $(APP) python -c \
		"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" \
		2>/dev/null || \
		docker run --rm python:3.11-slim python -c \
		"import secrets; print(secrets.token_urlsafe(50))"

env-check:
	@echo "$(CYAN)📋 Variables d'environnement chargées :$(RESET)"
	@[ -f .env ] && cat .env | grep -v "PASSWORD\|SECRET\|KEY" || echo "Aucun fichier .env trouvé"

.PHONY: help \
	dev dev-build stop restart logs logs-all shell manage status \
	migrate makemigrations makemigrations-app seed superuser dbshell reset-db static \
	prod-up prod-stop prod-restart prod-logs prod-logs-all prod-logs-nginx \
	prod-status prod-shell prod-manage prod-migrate prod-static prod-deploy prod-superuser \
	backup backup-local backup-list restore \
	ssl-init ssl-renew ssl-status \
	clean clean-all prune \
	check check-prod test secret-key env-check