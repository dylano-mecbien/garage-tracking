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
DIM   = \033[2m

# ════════════════════════════════════════════════════════════════════
#  AIDE COMPLÈTE
# ════════════════════════════════════════════════════════════════════

help:
	@echo ""
	@echo "$(BOLD)$(CYAN) ╔══════════════════════════════════════════════════════════╗$(RESET)"
	@echo "$(BOLD)$(CYAN) ║           Garage Suivi — Makefile $(DIM)v2.0$(RESET)$(BOLD)$(CYAN)              ║$(RESET)"
	@echo "$(BOLD)$(CYAN) ╚══════════════════════════════════════════════════════════╝$(RESET)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 🛠  DÉVELOPPEMENT$(RESET)"
	@echo "  $(CYAN)make dev$(RESET)               Démarrer l'environnement de développement"
	@echo "  $(CYAN)make dev-build$(RESET)         Rebuild + démarrer en dev"
	@echo "  $(CYAN)make stop$(RESET)              Arrêter les conteneurs dev"
	@echo "  $(CYAN)make restart$(RESET)           Redémarrer les conteneurs dev"
	@echo "  $(CYAN)make logs$(RESET)              Voir les logs dev en temps réel (web)"
	@echo "  $(CYAN)make logs-all$(RESET)          Voir les logs dev de tous les services"
	@echo "  $(CYAN)make shell$(RESET)             Ouvrir un shell bash dans le conteneur web"
	@echo "  $(CYAN)make manage cmd=...$(RESET)    Exécuter manage.py (ex: make manage cmd=createsuperuser)"
	@echo "  $(CYAN)make status$(RESET)            Voir l'état des conteneurs dev"
	@echo "  $(CYAN)make check$(RESET)             Vérifier le système Django (dev)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 🗄  BASE DE DONNÉES$(RESET)"
	@echo "  $(CYAN)make migrate$(RESET)           Appliquer toutes les migrations"
	@echo "  $(CYAN)make makemigrations$(RESET)    Créer les migrations pour toutes les apps"
	@echo "  $(CYAN)make makemigrations-app app=$(RESET)  Créer les migrations pour une app (ex: app=accounts)"
	@echo "  $(CYAN)make seed$(RESET)              Charger les données de démo (create_default_admin)"
	@echo "  $(CYAN)make superuser$(RESET)         Créer un super‑utilisateur (interactif)"
	@echo "  $(CYAN)make dbshell$(RESET)           Ouvrir un shell PostgreSQL interactif"
	@echo "  $(CYAN)make reset-db$(RESET)          ⚠️  Supprimer et recréer la base (dev uniquement)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 📦 STATIQUES & ASSETS$(RESET)"
	@echo "  $(CYAN)make static$(RESET)            Collecter les fichiers statiques (dev)"
	@echo "  $(CYAN)make prod-static$(RESET)       Collecter les fichiers statiques (prod)"
	@echo ""
	@echo "$(BOLD)$(RED) 🚀 PRODUCTION$(RESET)"
	@echo "  $(CYAN)make prod-up$(RESET)           Démarrer la production (build inclus)"
	@echo "  $(CYAN)make prod-stop$(RESET)         Arrêter la production"
	@echo "  $(CYAN)make prod-restart$(RESET)      Redémarrer la production"
	@echo "  $(CYAN)make prod-logs$(RESET)         Voir les logs web en temps réel"
	@echo "  $(CYAN)make prod-logs-all$(RESET)     Voir les logs de tous les services"
	@echo "  $(CYAN)make prod-logs-nginx$(RESET)   Voir les logs de Nginx"
	@echo "  $(CYAN)make prod-status$(RESET)       Voir l'état des conteneurs"
	@echo "  $(CYAN)make prod-shell$(RESET)        Shell bash dans le conteneur web"
	@echo "  $(CYAN)make prod-manage cmd=...$(RESET) Exécuter manage.py en prod"
	@echo "  $(CYAN)make prod-migrate$(RESET)      Migrer la base en production"
	@echo "  $(CYAN)make prod-deploy$(RESET)       Déployer une nouvelle version (pull + rebuild + migrer)"
	@echo "  $(CYAN)make prod-superuser$(RESET)    Créer un super‑utilisateur en prod"
	@echo "  $(CYAN)make prod-psql$(RESET)         Ouvrir un shell PostgreSQL en prod"
	@echo "  $(CYAN)make prod-check$(RESET)        Vérifier le système Django (--deploy)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 💾 SAUVEGARDES$(RESET)"
	@echo "  $(CYAN)make backup$(RESET)            Créer une sauvegarde de la base (prod)"
	@echo "  $(CYAN)make backup-local$(RESET)      Sauvegarder la base de développement"
	@echo "  $(CYAN)make backup-list$(RESET)       Lister les sauvegardes disponibles"
	@echo "  $(CYAN)make restore file=...$(RESET)  Restaurer une sauvegarde (ex: file=backups/backup_20250601.dump)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 🔐 SSL / CERTBOT$(RESET)"
	@echo "  $(CYAN)make ssl-init domain=...$(RESET)  Obtenir le certificat SSL (1ère fois)"
	@echo "  $(CYAN)make ssl-renew$(RESET)           Renouveler automatiquement le certificat"
	@echo "  $(CYAN)make ssl-status$(RESET)          Afficher l'état des certificats"
	@echo ""
	@echo "$(BOLD)$(GREEN) 🧹 NETTOYAGE$(RESET)"
	@echo "  $(CYAN)make clean$(RESET)            Arrêter et supprimer les conteneurs dev"
	@echo "  $(CYAN)make clean-all$(RESET)        ⚠️  Tout supprimer (conteneurs + volumes + images)"
	@echo "  $(CYAN)make prune$(RESET)            Nettoyer les images/volumes Docker inutilisés"
	@echo "  $(CYAN)make prod-clean$(RESET)       Arrêter et supprimer les conteneurs prod"
	@echo "  $(CYAN)make prod-clean-all$(RESET)   ⚠️  Supprimer tout en prod (conteneurs + volumes)"
	@echo ""
	@echo "$(BOLD)$(GREEN) 🔑 UTILITAIRES$(RESET)"
	@echo "  $(CYAN)make secret-key$(RESET)       Générer une nouvelle SECRET_KEY"
	@echo "  $(CYAN)make env-check$(RESET)        Afficher les variables d'environnement (sans secrets)"
	@echo "  $(CYAN)make test$(RESET)             Lancer les tests unitaires (dev)"
	@echo "  $(CYAN)make test-prod$(RESET)        Lancer les tests en production (--noinput)"
	@echo "  $(CYAN)make help$(RESET)             Afficher cette aide"
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

check:
	@echo "$(CYAN)🔍 Vérification du système Django (dev)...$(RESET)"
	$(DC) exec $(APP) python manage.py check

# ════════════════════════════════════════════════════════════════════
#  BASE DE DONNÉES (dev)
# ════════════════════════════════════════════════════════════════════

migrate:
	@echo "$(CYAN)🗄  Migration de la base de données (dev)...$(RESET)"
	$(DC) exec $(APP) python manage.py migrate
	@echo "$(GREEN)✅ Migrations appliquées$(RESET)"

makemigrations:
	@echo "$(CYAN)🗄  Création des migrations...$(RESET)"
	$(DC) exec $(APP) python manage.py makemigrations

makemigrations-app:
	@[ -n "$(app)" ] || (echo "$(RED)❌ Précisez l'application : make makemigrations-app app=accounts$(RESET)" && exit 1)
	@echo "$(CYAN)🗄  Création des migrations pour $(app)...$(RESET)"
	$(DC) exec $(APP) python manage.py makemigrations $(app)

seed:
	@echo "$(CYAN)🌱 Chargement des données de démo...$(RESET)"
	$(DC) exec $(APP) python manage.py create_default_admin || echo "⚠️  Commande create_default_admin inexistante, utilisation de createsuperuser..."
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
#  STATIQUES (dev)
# ════════════════════════════════════════════════════════════════════

static:
	@echo "$(CYAN)📦 Collecte des fichiers statiques (dev)...$(RESET)"
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
	@echo "$(CYAN)⚙️  Exécution: python manage.py $(cmd) (prod)$(RESET)"
	$(DC_PROD) exec $(APP) python manage.py $(cmd)

prod-migrate:
	@echo "$(CYAN)🗄  Migration en production...$(RESET)"
	$(DC_PROD) exec $(APP) python manage.py migrate --noinput
	@echo "$(GREEN)✅ Migrations prod appliquées$(RESET)"

prod-static:
	@echo "$(CYAN)📦 Collecte statiques prod...$(RESET)"
	$(DC_PROD) exec $(APP) python manage.py collectstatic --noinput
	@echo "$(GREEN)✅ Fichiers statiques collectés$(RESET)"

prod-deploy:
	@echo "$(GREEN)🚀 Déploiement nouvelle version...$(RESET)"
	git pull
	$(DC_PROD) up -d --build $(APP)
	$(MAKE) prod-migrate
	$(MAKE) prod-static
	$(DC_PROD) restart nginx
	@echo "$(GREEN)✅ Déploiement terminé$(RESET)"

prod-superuser:
	@echo "$(CYAN)👤 Création d'un super-utilisateur en prod...$(RESET)"
	$(DC_PROD) exec $(APP) python manage.py createsuperuser

prod-psql:
	@echo "$(CYAN)🗄  Shell PostgreSQL en production...$(RESET)"
	$(DC_PROD) exec $(DB) psql -U $${DB_USER:-garage_user} -d $${DB_NAME:-garage_db}

prod-check:
	@echo "$(CYAN)🔍 Vérification système Django (prod)...$(RESET)"
	$(DC_PROD) exec $(APP) python manage.py check --deploy

prod-clean:
	@echo "$(YELLOW)🧹 Arrêt et suppression des conteneurs prod...$(RESET)"
	$(DC_PROD) down

prod-clean-all:
	@echo "$(RED)⚠️  Suppression de TOUT en production (conteneurs + volumes)$(RESET)"
	@read -p "Confirmer ? (oui/non) : " confirm && [ "$$confirm" = "oui" ] || exit 1
	$(DC_PROD) down -v
	@echo "$(GREEN)✅ Nettoyage complet de la prod$(RESET)"

# ════════════════════════════════════════════════════════════════════
#  SAUVEGARDES
# ════════════════════════════════════════════════════════════════════

backup:
	@echo "$(CYAN)💾 Sauvegarde de la base de production...$(RESET)"
	@mkdir -p backups
	$(DC_PROD) exec -T $(DB) pg_dump \
		-U $${DB_USER:-garage_user} \
		$${DB_NAME:-garage_db} \
		-F c \
		> backups/backup_$$(date +%Y%m%d_%H%M%S).dump
	@echo "$(GREEN)✅ Sauvegarde créée dans ./backups/$(RESET)"
	@ls -lh backups/*.dump | tail -1

backup-local:
	@echo "$(CYAN)💾 Sauvegarde de la base de développement...$(RESET)"
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
		-U $${DB_USER:-garage_user} \
		-d $${DB_NAME:-garage_db} \
		-c --if-exists \
		< $(file)
	@echo "$(GREEN)✅ Restauration terminée$(RESET)"

# ════════════════════════════════════════════════════════════════════
#  SSL / CERTBOT
# ════════════════════════════════════════════════════════════════════

ssl-init:
	@[ -n "$(domain)" ] || (echo "$(RED)❌ Précisez le domaine : make ssl-init domain=garage.laprudenceplus-cm.com$(RESET)" && exit 1)
	@echo "$(CYAN)🔐 Obtention du certificat SSL pour $(domain)...$(RESET)"
	$(DC_PROD) up -d nginx
	docker run --rm \
		-v $(PWD)/certbot_certs:/etc/letsencrypt \
		-v $(PWD)/certbot_www:/var/www/certbot \
		certbot/certbot certonly --webroot \
		-w /var/www/certbot \
		-d $(domain) \
		--email $${ADMIN_EMAIL:-admin@$(domain)} \
		--agree-tos --no-eff-email
	@echo "$(GREEN)✅ Certificat SSL obtenu$(RESET)"
	$(DC_PROD) restart nginx

ssl-renew:
	@echo "$(CYAN)🔄 Renouvellement du certificat SSL...$(RESET)"
	docker run --rm \
		-v $(PWD)/certbot_certs:/etc/letsencrypt \
		-v $(PWD)/certbot_www:/var/www/certbot \
		certbot/certbot renew --quiet --webroot -w /var/www/certbot
	$(DC_PROD) exec nginx nginx -s reload
	@echo "$(GREEN)✅ SSL renouvelé$(RESET)"

ssl-status:
	@echo "$(CYAN)📋 État des certificats SSL :$(RESET)"
	docker run --rm \
		-v garage-tracking_certbot_certs:/etc/letsencrypt \
		certbot/certbot certificates

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
#  UTILITAIRES
# ════════════════════════════════════════════════════════════════════

secret-key:
	@echo "$(CYAN)🔑 Génération d'une nouvelle SECRET_KEY :$(RESET)"
	@$(DC) exec $(APP) python -c \
		"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" \
		2>/dev/null || \
		docker run --rm python:3.11-slim python -c \
		"import secrets; print(secrets.token_urlsafe(50))"

env-check:
	@echo "$(CYAN)📋 Variables d'environnement chargées (dev) :$(RESET)"
	@[ -f .env ] && cat .env | grep -v "PASSWORD\|SECRET\|KEY" || echo "Aucun fichier .env trouvé"

test:
	@echo "$(CYAN)🧪 Lancement des tests (dev)...$(RESET)"
	$(DC) exec $(APP) python manage.py test --verbosity=2 --noinput

test-prod:
	@echo "$(CYAN)🧪 Lancement des tests (prod)...$(RESET)"
	$(DC_PROD) exec $(APP) python manage.py test --verbosity=2 --noinput

# ════════════════════════════════════════════════════════════════════
#  DÉCLARATIONS .PHONY
# ════════════════════════════════════════════════════════════════════

.PHONY: help \
	dev dev-build stop restart logs logs-all shell manage status check \
	migrate makemigrations makemigrations-app seed superuser dbshell reset-db static \
	prod-up prod-stop prod-restart prod-logs prod-logs-all prod-logs-nginx \
	prod-status prod-shell prod-manage prod-migrate prod-static prod-deploy \
	prod-superuser prod-psql prod-check prod-clean prod-clean-all \
	backup backup-local backup-list restore \
	ssl-init ssl-renew ssl-status \
	clean clean-all prune \
	secret-key env-check test test-prod