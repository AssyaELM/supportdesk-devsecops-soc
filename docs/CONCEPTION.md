# Conception — SupportDesk

Application locale à déployer séparément dans Kind, sans intervention sur Kali depuis Codex.

## Architecture

Navigateur → Nginx non privilégié (React et proxy /api) → FastAPI → PostgreSQL 16.
Développement : Vite utilise le même chemin /api avec un proxy vers FastAPI.
Kubernetes : namespace existant secrets-app, Service postgres:5432 et Secret postgres-credentials (clé POSTGRES_PASSWORD). Aucun manifest PostgreSQL, PVC ou Namespace n'est créé.

## Données

- users : identité fictive, e-mail unique, hash Argon2id, rôle user/admin, état actif, clé de peuplement unique facultative.
- sessions : hash du jeton opaque, hash CSRF, expiration UTC, utilisateur. Aucun jeton brut en base.
- password_resets : hash du jeton à usage unique, expiration, utilisateur.
- categories : catégories uniques.
- tickets : séquence d'identifiants, titre, description, catégorie, priorité, statut, demandeur et administrateur affecté, dates UTC, clé de démonstration unique.
- messages : auteur, texte, visibilité publique/interne.
- ticket_history : acteur, champ changé, anciennes/nouvelles valeurs, horodatage.
- audit_events : métadonnées limitées, type, résultat, acteur, rôle, requête, ressource et indicateur demo.

## Sécurité

Cookies HttpOnly, SameSite=Lax ; Secure obligatoire en production HTTPS. Protection CSRF sur les mutations authentifiées et contrôle Origin sur les mutations. Permissions et propriété vérifiées dans l'API, y compris pour les notes internes. Sessions révoquées lors de la désactivation ou du changement de mot de passe. Limitation des tentatives de connexion en base via les événements récents, réponse générique aux identifiants invalides. Pas d'inscription publique. Création initiale et peuplement via CLI explicite uniquement en développement.

Les réinitialisations sont désactivées par défaut. Un mode demo explicite permet à un administrateur de générer un lien temporaire pour un compte de démonstration ; aucun courriel n'est prétendument envoyé. Les invitations, pièces jointes et notifications par courriel sont présentées comme indisponibles et non simulées.

## Référence visuelle

Les cinq planches du dossier voisin mockups sont la référence : navigation latérale marine, fond clair, cartes blanches, boutons bleus et badges textuels. On harmonise les incohérences des images générées : priorité Moyenne partout, mêmes catégories et mêmes données PostgreSQL. Le mobile conserve des cartes et une navigation repliable.

## Secrets et rotation

DB_PASSWORD ou DB_PASSWORD_FILE, jamais dans le frontend. Le processus lit sa configuration au démarrage : après une modification d'un Secret injecté par ESO, un redémarrage contrôlé du backend est requis. Une mise à jour de Secret seule ne renouvelle ni le mot de passe PostgreSQL ni les variables d'un processus existant. Aucune installation de Vault, ESO, Falco ou Splunk à cette étape.
