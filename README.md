# SupportDesk

SupportDesk est une application de gestion des demandes de support informatique : les employés créent et suivent leurs tickets ; les administrateurs traitent les demandes, répondent aux utilisateurs et gèrent les comptes. Elle sert de support à un laboratoire DevSecOps, Kubernetes, gestion des secrets et SOC.

Le navigateur communique avec FastAPI par `/api`. Les données et statistiques proviennent de PostgreSQL. Les identifiants de base de données restent côté backend.

## Technologies

| Partie | Technologies présentes |
| --- | --- |
| Interface | React 19, TypeScript, React Router 7, Vite 7, CSS responsive |
| API | Python 3.12 dans Docker, FastAPI, Pydantic, SQLAlchemy 2 |
| Base et migrations | PostgreSQL 16, Psycopg 3, Alembic |
| Authentification | Argon2id, sessions opaques stockées sous forme hachée, cookie HttpOnly, protection CSRF |
| Infrastructure | Docker Compose, Nginx non privilégié, manifests Kubernetes pour Kind |
| Tests | Pytest, HTTPX et TestClient FastAPI, PostgreSQL isolé |

Les versions des dépendances sont définies dans `backend/requirements.txt`, `frontend/package.json` et `frontend/pnpm-lock.yaml`.

## Arborescence

```text
supportdesk/
├── backend/
│   ├── app/
│   │   ├── main.py                 # Routes, autorisations et audit JSON
│   │   ├── config.py               # Configuration par environnement/fichier secret
│   │   ├── db.py                   # Connexion SQLAlchemy
│   │   ├── models.py               # Modèles PostgreSQL
│   │   ├── schemas.py              # Validation des entrées
│   │   └── security.py             # Hachage et vérification
│   ├── alembic.ini
│   ├── requirements.txt
│   └── Dockerfile
├── database/
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/0001_initial.py
│   └── seed.py
├── frontend/
│   ├── src/                       # React, API, types et CSS
│   ├── public/assets/             # Référence graphique utilisée par la connexion
│   ├── dist/                      # Résultat du build local présent
│   ├── index.html
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── pnpm-workspace.yaml
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── nginx.conf
│   └── Dockerfile
├── deploy/kubernetes/
│   ├── app.yaml                   # ConfigMap, ServiceAccounts, Deployments et Services
│   └── migrate.yaml               # Job Alembic explicite
├── tests/
│   ├── conftest.py
│   └── test_api.py
├── docs/CONCEPTION.md
├── docker-compose.yml
├── pytest.ini
├── .env.example
├── .gitignore
├── .dockerignore
└── README.md
```

## Prérequis

- Windows avec PowerShell et Docker Desktop démarré en mode conteneurs Linux.
- Docker Compose v2, accessible par `docker compose`.
- Accès aux registres Docker, Python et Node lors du premier build.
- Ports locaux `8080` et `55432` disponibles.
- Pour les étapes ultérieures sur Kali : Docker, Kind, kubectl et accès au contexte `kind-secrets-soc-lab`.

Python et Node installés sur Windows ne sont pas nécessaires pour le parcours Docker décrit ci-dessous. Les conteneurs fournissent leurs environnements.

## Démarrage sous Windows avec Docker Compose

Toutes les commandes PowerShell suivantes s'exécutent depuis la racine du projet :

```powershell
Set-Location 'C:\Users\HP\Documents\Codex\2026-11-05\maiennatnt-j-ai-chosit-a-frealiser\outputs\supportdesk'
```

Créer `.env` uniquement s'il n'existe pas, sans écraser une configuration déjà présente :

```powershell
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
notepad .env
```

Renseigner `DB_PASSWORD` avec un mot de passe local choisi. Pour une première démonstration, configurer également :

```dotenv
APP_ENV=development
DEMO_SEED_ENABLED=true
DEMO_PASSWORD=<mot-de-passe-de-demonstration-au-moins-12-caracteres>
```

Remplacer la valeur entre chevrons ; aucun mot de passe par défaut n'est fourni. Le fichier `.env` est ignoré par Git et exclu des images. Les adresses des deux comptes principaux sont configurables par `DEMO_USER_EMAIL` et `DEMO_ADMIN_EMAIL`.

Compose impose `DB_HOST=postgres` et `DB_PORT=5432` dans les conteneurs : les valeurs hôte de `.env` ne changent pas ces paramètres internes. Depuis Windows, ce PostgreSQL local est publié sur `localhost:55432`.

Construire et démarrer :

```powershell
docker compose up -d --build
docker compose ps -a
```

Compose attend PostgreSQL, exécute automatiquement le service `migrate`, démarre le backend puis le frontend. Un service `migrate` terminé avec le code `0` est normal. Le peuplement n'est pas automatique.

Après le peuplement décrit ci-dessous, ouvrir [SupportDesk](http://localhost:8080). Le frontend Nginx transmet `/api` au backend ; le port backend n'est pas publié sur Windows.

Pour consulter les journaux ou arrêter les services en conservant le volume :

```powershell
docker compose logs --tail 100 backend frontend migrate
docker compose stop
```

Le volume `supportdesk-data` conserve les données. Ne pas utiliser `docker compose down -v` pour un arrêt normal. Sur un volume déjà initialisé, modifier `DB_PASSWORD` dans `.env` ne change pas le mot de passe PostgreSQL existant : conserver les identifiants correspondants ou planifier une rotation séparée.

## Migrations et données fictives

### Exécuter explicitement les migrations

En plus du démarrage automatique par Compose, les migrations peuvent être exécutées explicitement :

```powershell
docker compose run --rm migrate
```

Cette commande utilise `backend/alembic.ini` et exécute `alembic upgrade head`. Elle crée les tables applicatives préfixées `sd_` et la table de suivi Alembic. La migration initiale refuse le downgrade destructif.

### Exécuter explicitement le peuplement

Vérifier `APP_ENV=development`, `DEMO_SEED_ENABLED=true` et un `DEMO_PASSWORD` d'au moins 12 caractères dans `.env`, puis lancer :

```powershell
docker compose --profile demo run --rm seed
```

Le script `database/seed.py` ajoute dans PostgreSQL :

- 8 comptes utilisateurs et 2 administrateurs fictifs ;
- 7 catégories et 30 tickets répartis entre les quatre statuts ;
- des messages publics, notes internes, affectations et historiques ;
- des événements d'audit marqués `demo=true` et `source=demo_seed`.

Le script est idempotent : une seconde exécution ne recrée pas les entrées déjà identifiées par leurs clés de démonstration. Il ne supprime pas les données et ne remplace pas les comptes ou tickets existants. Il refuse les collisions avec des comptes existant hors de son peuplement. Changer `DEMO_PASSWORD` après peuplement ne modifie pas les mots de passe des comptes déjà créés.

Comptes principaux par défaut :

| Rôle | Adresse |
| --- | --- |
| Utilisateur | `assia.benkacem@example.org` |
| Administrateur | `youssef.amrani@example.org` |

À leur création, ces comptes utilisent le mot de passe défini par `DEMO_PASSWORD`, enregistré uniquement sous forme hachée dans PostgreSQL. Le peuplement est interdit lorsque `APP_ENV=production`.

### Réinitialisation en mode démonstration

Pour activer le mode prévu dans le code, définir `RESET_MODE=demo` dans `.env`, puis recréer le backend :

```powershell
docker compose up -d backend
```

Un administrateur peut alors générer un lien de réinitialisation pour un compte de démonstration actif depuis la page Utilisateurs. Le lien est à usage unique et valable 15 minutes. Aucun e-mail n'est envoyé. Le mode est désactivé par défaut et interdit en production.

## Tests

Les tests utilisent exclusivement une base nommée `supportdesk_test`. Ils ne doivent pas être dirigés vers la base Kubernetes. Ils créent le schéma dans cette base dédiée, peuplent chaque scénario et annulent les transactions de chaque test. Utiliser une base de test vide et réservée à cet usage pour conserver les assertions de comptage.

Avec le PostgreSQL Compose local démarré, créer cette base une seule fois :

```powershell
docker compose exec postgres createdb -U appuser supportdesk_test
```

Si `DB_USER` a été personnalisé, remplacer `appuser` dans cette commande. Si la base existe déjà, ne pas la supprimer : passer directement aux tests si elle est bien dédiée à SupportDesk.

Le Dockerfile backend n'embarque pas le dossier `tests` ; le monter en lecture seule avec sa configuration Pytest :

```powershell
docker compose run --rm --no-deps -e SUPPORTDESK_TEST_DB=supportdesk_test -v "${PWD}/tests:/app/tests:ro" -v "${PWD}/pytest.ini:/app/pytest.ini:ro" backend python -m pytest -q
```

`DEMO_PASSWORD` doit être renseigné et contenir au moins 12 caractères. Les fixtures activent elles-mêmes le peuplement et le reset de démonstration dans le processus de test. Sans `SUPPORTDESK_TEST_DB=supportdesk_test`, les tests dépendant de la base sont ignorés, ce qui ne constitue pas une validation réussie.

La suite couvre notamment l'idempotence du seed, le hachage, l'authentification, les permissions, les notes internes, CSRF, la création et résolution des tickets, les statistiques, la révocation des sessions, les resets et la non-divulgation de secrets dans les données d'audit.

Pour un build frontend hors Docker, avec Node compatible Vite 7 et pnpm 11.25.0 installés :

```powershell
Set-Location frontend
pnpm install --frozen-lockfile
pnpm run build
Set-Location ..
```

Le script `build` lance TypeScript puis Vite. Les parcours dans un navigateur et le comportement Docker/Kubernetes doivent également être vérifiés ; une compilation seule ne les valide pas.

## Préparation du déploiement Kubernetes sur Kali

Cette section décrit les commandes à exécuter ultérieurement sur Kali, depuis une copie du projet. Elle n'implique aucun déploiement automatique depuis Windows.

### Ressources attendues

- Cluster Kind `secrets-soc-lab` et contexte `kind-secrets-soc-lab`.
- Namespace `secrets-app` déjà présent.
- Service PostgreSQL `postgres:5432`, base `appdb`, utilisateur `appuser`.
- Secret `postgres-credentials`, avec la clé `POSTGRES_PASSWORD`.
- PostgreSQL et son PVC existants, conservés sans modification.

Transférer le code du projet vers Kali sans `.env`, `node_modules`, caches ni identifiants locaux Windows. Aucun manifest du projet ne crée PostgreSQL, son Secret ou son PVC.

### Construire et charger les images

Depuis la racine du projet sur Kali :

```bash
docker build -f backend/Dockerfile -t supportdesk-backend:local .
docker build -f frontend/Dockerfile -t supportdesk-frontend:local .
kind load docker-image supportdesk-backend:local supportdesk-frontend:local --name secrets-soc-lab
```

Ces noms correspondent exactement aux images référencées par les manifests.

### Examiner les manifests avant toute application

- `deploy/kubernetes/app.yaml` contient la configuration non sensible, deux ServiceAccounts sans montage automatique de token, deux Deployments et leurs Services.
- Le backend reçoit son mot de passe depuis le Secret existant ; aucune valeur de mot de passe n'est incluse.
- Les probes backend sont `/health` et `/ready` ; le frontend expose `/health`.
- Une réplique par composant est prévue, avec limites CPU et mémoire et exécution non privilégiée.
- `deploy/kubernetes/migrate.yaml` contient un Job Alembic qui ajoutera les tables SupportDesk dans `appdb`. Prévoir une sauvegarde et vérifier la base cible avant cette opération.
- La configuration fournie est un laboratoire HTTP local : `APP_ENV=development`, origine autorisée `http://localhost:8080`, reset et seed désactivés. Pour une autre URL, adapter l'origine avant déploiement. Pour une production HTTPS, prévoir TLS et `COOKIE_SECURE=true` ; les manifests ne fournissent pas cette terminaison TLS.

Après cette revue et lors de la séance de déploiement séparée :

```bash
kubectl --context kind-secrets-soc-lab -n secrets-app apply -f deploy/kubernetes/app.yaml
kubectl --context kind-secrets-soc-lab -n secrets-app apply -f deploy/kubernetes/migrate.yaml
kubectl --context kind-secrets-soc-lab -n secrets-app wait --for=condition=complete job/supportdesk-migrate-v1 --timeout=120s
kubectl --context kind-secrets-soc-lab -n secrets-app rollout status deployment/backend --timeout=120s
kubectl --context kind-secrets-soc-lab -n secrets-app rollout status deployment/frontend --timeout=120s
kubectl --context kind-secrets-soc-lab -n secrets-app port-forward service/frontend 8080:8080
```

Avant la fin des migrations, le backend peut rester non prêt : `/ready` vérifie l'accès au schéma applicatif. Le Job n'est pas réexécuté automatiquement quand un Job du même nom est déjà terminé ; toute nouvelle migration devra faire l'objet d'une procédure explicite.

Le port-forward rend l'interface accessible depuis le navigateur de Kali à `http://localhost:8080`. Les manifests ne déclenchent aucun peuplement et ne créent aucun compte. Un peuplement éventuel de la base du laboratoire devra être décidé et exécuté séparément ; ne pas réutiliser implicitement les identifiants Windows.

Les manifests présents ne fournissent pas encore les NetworkPolicy, règles d'admission personnalisées ni l'intégration Vault/ESO/Falco/Splunk. Vérifier les politiques réseau existantes : les flux frontend → backend, backend → PostgreSQL et DNS doivent être autorisés selon le besoin.

### Préparation des secrets et de leur rotation

Le backend accepte `DB_PASSWORD` ou `DB_PASSWORD_FILE` avec les autres variables `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`. Le support fichier existe dans le code, mais Compose et les manifests fournis utilisent la variable `DB_PASSWORD` ; un montage devra être ajouté séparément pour utiliser un fichier.

La configuration est lue au démarrage. Après une rotation coordonnée des identifiants PostgreSQL et du Secret Kubernetes, redémarrer le backend pour prendre en compte la nouvelle valeur :

```bash
kubectl --context kind-secrets-soc-lab -n secrets-app rollout restart deployment/backend
```

Modifier uniquement un Secret ne modifie pas le mot de passe du rôle PostgreSQL et ne recharge pas les variables d'un processus déjà lancé. La rotation, sa validation et l'intégration External Secrets Operator restent une étape distincte.

## Fonctionnalités disponibles et limites

### Implémentées

- Connexion/déconnexion, expiration des sessions et pages privées.
- Hachage Argon2id, protection CSRF, contrôle des rôles et propriété des tickets côté API.
- Tableaux de bord alimentés par PostgreSQL.
- Création, consultation, recherche et filtres de tickets, avec pagination.
- Statuts Nouveau, En cours, En attente et Résolu ; priorités Basse, Moyenne et Haute.
- Conversation publique, historique et notes internes réservées aux administrateurs.
- Affectation, changement de priorité et de statut, résumé de résolution.
- Consultation des comptes et activation/désactivation ; révocation des sessions à la désactivation.
- Modification du nom et du mot de passe ; adresse e-mail non modifiable depuis le profil.
- États de chargement, erreurs, listes vides et disposition responsive.
- Journalisation JSON pour le futur SOC, sans mots de passe ni jetons ; événements fictifs identifiés dans les données de seed.
- Réinitialisation à usage unique en mode démonstration explicite.

### Indisponibles ou restant à vérifier

- Inscription publique : volontairement absente.
- Invitations, réinitialisation par e-mail et notifications par e-mail : aucun envoi SMTP implémenté.
- Pièces jointes : indisponibles et signalées comme telles dans l'interface.
- Création de nouveaux comptes depuis l'interface : non implémentée ; le peuplement crée les comptes fictifs.
- Intégration Vault, External Secrets Operator, Falco et Splunk : non installée à cette étape.
- Fidélité visuelle complète aux cinq planches et parcours navigateur exhaustifs : validation restant à terminer.
- Images applicatives Docker et déploiement Kubernetes : validation à effectuer séparément ; la présence des Dockerfiles et manifests ne garantit pas leur exécution dans l'environnement final.

Consulter `docs/CONCEPTION.md` pour les choix d'architecture. Aucune commande de suppression des données n'est nécessaire au parcours décrit ici.
