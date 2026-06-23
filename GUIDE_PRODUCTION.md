# 🚀 Guide de mise en production — Garage Suivi

## 1. Préparer le serveur (VPS)

Choisissez un fournisseur : **Contabo, Hetzner, OVH, DigitalOcean, AWS Lightsail**.
Minimum recommandé : **2 vCPU / 4 Go RAM / 40 Go SSD**.

```bash
# Se connecter en SSH
ssh root@VOTRE_IP_SERVEUR

# Mettre à jour le système
apt update && apt upgrade -y

# Installer Docker + Docker Compose
curl -fsSL https://get.docker.com | sh
apt install docker-compose-plugin -y

# Créer un utilisateur non-root (sécurité)
adduser deploy
usermod -aG docker deploy
su - deploy
```

## 2. Pointer le nom de domaine

Chez votre registrar (Namecheap, OVH, Google Domains...) :
- Créez un enregistrement **A** : `garage.votredomaine.com` → IP du serveur
- Attendez la propagation DNS (5 min à 24h) — vérifiez avec :
```bash
nslookup garage.votredomaine.com
```

## 3. Configurer le firewall

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

## 4. Transférer le projet sur le serveur

```bash
# Depuis votre machine locale
scp -r garage_suivi/ deploy@VOTRE_IP:/home/deploy/

# Ou via Git (recommandé)
git clone https://github.com/dylano-mecbien/garage-tracking.git
cd garage_suivi
```

## 5. Ajouter les fichiers de production

Copiez ces fichiers fournis dans le projet :

| Fichier fourni | Destination dans le projet |
|---|---|
| `production.py` | `garage/settings/production.py` |
| `docker-compose.prod.yml` | racine du projet |
| `Dockerfile.prod` | racine du projet |
| `nginx.prod.conf` | `nginx/nginx.prod.conf` |
| `.env.production.example` | renommer en `.env` à la racine |

```bash
mkdir -p nginx backups
# placez nginx.prod.conf dans nginx/
# placez .env à la racine (rempli avec vos vraies valeurs)
```

⚠️ **Éditez `.env`** avec vos vraies valeurs (mots de passe forts, domaine réel).

Générez une `SECRET_KEY` :
```bash
docker run --rm python:3.11-slim python -c \
"import secrets; print(secrets.token_urlsafe(50))"
```

## 6. Obtenir le certificat SSL (première fois)

Avant le premier lancement, on doit générer le certificat Let's Encrypt :

```bash
# Lancer temporairement nginx seul (sans SSL) pour le challenge
docker compose -f docker-compose.prod.yml up -d nginx

# Demander le certificat
docker run --rm \
  -v $(pwd)/certbot_certs:/etc/letsencrypt \
  -v $(pwd)/certbot_www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d garage.votredomaine.com \
  --email dylanogold@gmail.com --agree-tos --no-eff-email
```

## 7. Lancer l'application complète

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Vérifiez que tout tourne :
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f web
```

## 8. Initialiser la base de données

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```


## 9. Vérifications post-déploiement

```bash
# Tester le HTTPS
curl -I https://garage.votredomaine.com

# Vérifier les en-têtes de sécurité
curl -I https://garage.votredomaine.com | grep -i strict

# Tester depuis le navigateur :
# https://garage.votredomaine.com
```

Utilisez aussi : https://www.ssllabs.com/ssltest/ pour noter votre config SSL.

## 10. Sauvegardes

Le service `backup` dans `docker-compose.prod.yml` sauvegarde automatiquement la base toutes les 24h dans `./backups/`.

**Récupérer une sauvegarde sur votre machine :**
```bash
scp deploy@VOTRE_IP:/home/deploy/garage_suivi/backups/backup_XXXX.dump ./
```

**Restaurer une sauvegarde :**
```bash
docker compose -f docker-compose.prod.yml exec -T db \
  pg_restore -U garage_prod_user -d garage_db_prod -c /backups/backup_XXXX.dump
```

⚠️ **Recommandé en plus** : copiez régulièrement `./backups/` vers un stockage externe (S3, Google Drive, autre serveur) — un crash disque détruit les sauvegardes locales aussi.

## 11. Monitoring des erreurs (Sentry — gratuit jusqu'à 5k events/mois)

1. Créez un compte sur https://sentry.io
2. Créez un projet "Django"
3. Copiez le DSN dans `.env` → `SENTRY_DSN=https://...`
4. Relancez : `docker compose -f docker-compose.prod.yml up -d --build web`

Vous recevrez désormais un email à chaque erreur 500 en production.

## 12. Mises à jour futures

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build web
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

## 13. Renouvellement SSL automatique

Le service `certbot` dans le compose se charge du renouvellement automatique toutes les 12h (Let's Encrypt expire après 90 jours). Aucune action manuelle nécessaire après la configuration initiale.

---

## ⚠️ Points de sécurité à ne JAMAIS oublier

- [ ] `DEBUG = False` en production (sinon fuite d'infos sensibles sur erreur)
- [ ] `SECRET_KEY` unique, jamais celle du développement, jamais sur GitHub
- [ ] `.env` dans `.gitignore` — ne jamais commiter les mots de passe
- [ ] Mots de passe DB/Redis forts (32+ caractères aléatoires)
- [ ] Supprimer/changer les comptes de démo (`admin@garage.cm / Garage@Admin2024`)
- [ ] HTTPS obligatoire (`SECURE_SSL_REDIRECT = True`)
- [ ] Sauvegardes testées (faites un essai de restauration avant d'en avoir besoin)
- [ ] Firewall actif, seuls SSH/80/443 ouverts
- [ ] Utilisateur Docker non-root (`Dockerfile.prod` le fait déjà)

## 🆘 Dépannage rapide

| Problème | Commande |
|---|---|
| Voir les logs en direct | `docker compose -f docker-compose.prod.yml logs -f web` |
| Erreur 502 Bad Gateway | Vérifier que `web` est `healthy` : `docker compose ps` |
| SSL ne fonctionne pas | Vérifier les chemins certbot et que le DNS est bien propagé |
| Base de données inaccessible | `docker compose exec db psql -U $DB_USER -d $DB_NAME` |
| Reset complet (⚠️ perte de données) | `docker compose -f docker-compose.prod.yml down -v` |
