# DOC-01_Konnaxion_Product_Vision.md

```yaml id="doc01-meta"
doc_id: DOC-01
title: Konnaxion Product Vision
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
canonical_terms:
  - Konnaxion
  - Konnaxion Capsule
  - Konnaxion Capsule Manager
  - Konnaxion Agent
  - Konnaxion Box
  - Konnaxion Instance
  - KX_*
```

---

# 1. Vision produit

**Konnaxion** doit devenir une plateforme collaborative, éducative, civique et créative pouvant être déployée comme une **appliance portable, sécurisée et plug-and-play**.

La cible produit n’est pas seulement une application web hébergée sur un VPS. La cible est :

```text id="vision-target"
Konnaxion dans une capsule,
installable sur une machine dédiée,
opérable en intranet,
activable en démo privée ou publique temporaire,
avec configuration minimale,
sécurité intégrée,
et déploiement reproductible.
```

Konnaxion v14 existe déjà comme plateforme modulaire avec plusieurs domaines fonctionnels : **Kollective Intelligence**, **ethiKos**, **Konsultations**, **KeenKonnect**, **KonnectED** et **Kreative**. Ces domaines couvrent la réputation/expertise, le vote pondéré, les débats structurés, les consultations, les projets collaboratifs, l’éducation, les portfolios, les ressources de connaissance, la création culturelle et la conservation numérique. 

---

# 2. Formule produit

La formulation officielle du produit cible est :

```text id="product-formula"
Konnaxion = plateforme applicative modulaire
Konnaxion Capsule = format portable signé
Konnaxion Capsule Manager = application de gestion plug-and-play
Konnaxion Agent = service système sécurisé
Konnaxion Box = machine dédiée prête à l’emploi
Konnaxion Instance = installation active avec données, secrets et état runtime
```

Le produit doit permettre à une organisation de brancher une machine, démarrer Konnaxion, choisir un mode réseau, et obtenir une URL fonctionnelle sans comprendre Docker, Traefik, PostgreSQL, Redis, Celery, ports, certificats ou fichiers `.env`.

---

# 3. Positionnement

Konnaxion doit être positionné comme :

```text id="positioning"
Une plateforme modulaire de collaboration, consultation, intelligence collective,
apprentissage, portfolio, projets et création culturelle,
déployable en mode souverain, local, intranet ou public contrôlé.
```

Ce n’est pas :

```text id="not-positioning"
un simple site web
un simple CMS
un simple dashboard Docker
une app SaaS seulement
un projet dépendant d’un seul VPS public
```

---

# 4. Objectif principal

L’objectif principal est de transformer Konnaxion en système :

```text id="main-objective"
portable
reproductible
privé par défaut
sécurisé par défaut
opérable sans expertise DevOps
installable en local ou intranet
extensible vers le web public lorsque nécessaire
```

Cela répond directement aux leçons du déploiement précédent : le VPS Namecheap a été compromis, avec conteneurs malveillants, persistence cron, miner, `/tmp/sshd`, tentative de backdoor sudo et secrets exposés. La nouvelle vision doit donc intégrer la sécurité dans le produit lui-même, pas seulement dans une procédure de déploiement. 

---

# 5. Publics cibles

## 5.1 Opérateur non technique

Personne qui doit démarrer Konnaxion sans comprendre l’infrastructure.

Exemples :

```text id="operator-persona"
enseignant
facilitateur
responsable d’organisme
coordinateur de projet
animateur de consultation
responsable de laboratoire citoyen
```

Besoin :

```text id="operator-need"
brancher
démarrer
choisir le mode réseau
ouvrir l’URL
gérer backup/restore de base
```

## 5.2 Administrateur technique léger

Personne capable d’utiliser une interface d’administration, mais pas nécessairement de maintenir une stack complète.

Besoin :

```text id="admin-need"
voir l’état système
changer le mode réseau
ouvrir un tunnel temporaire
faire un backup
appliquer une mise à jour
restaurer une instance
consulter les logs
```

## 5.3 Développeur Konnaxion

Personne qui construit les capsules.

Besoin :

```text id="developer-need"
builder frontend/backend
exécuter tests
construire images Docker
générer manifest
signer capsule
publier .kxcap
valider sécurité
```

## 5.4 Organisation hôte

École, municipalité, OBNL, collectif, centre culturel, laboratoire, communauté ou équipe projet.

Besoin :

```text id="org-need"
contrôle local
mode intranet
démo privée
données sous contrôle
installation simple
fonctionnement sans dépendre d’un SaaS externe
```

---

# 6. Problème à résoudre

Le problème n’est pas seulement de “déployer Konnaxion”.

Le problème est :

```text id="problem"
Déployer une application complexe de manière fiable,
sans exposer les services internes,
sans dépendre d’un administrateur DevOps,
sans recréer les failles du VPS compromis,
et sans rendre l’installation trop complexe pour un contexte de démo ou intranet.
```

Konnaxion utilise déjà une stack complète : backend **Django 5.1 + Django REST Framework + Celery + Redis**, frontend **Next.js/React**, base **PostgreSQL** en production, et Redis comme broker/résultat Celery.  Cette complexité doit être masquée derrière une expérience plug-and-play.

---

# 7. Solution produit

La solution cible est une architecture en quatre couches :

```text id="solution-layers"
1. Konnaxion Capsule
   Format portable signé contenant l’application et sa configuration déclarative.

2. Konnaxion Capsule Manager
   Interface locale qui importe, démarre, arrête, met à jour et surveille une instance.

3. Konnaxion Agent
   Service système privilégié, limité et audité, qui contrôle Docker, firewall, réseau et backups.

4. Konnaxion Runtime
   Stack Docker Compose isolée exécutant Traefik, Next.js, Django, PostgreSQL, Redis, Celery et Nginx/media.
```

---

# 8. Expérience utilisateur cible

## 8.1 Premier démarrage

L’expérience idéale :

```text id="first-run"
1. Brancher la Konnaxion Box.
2. Ouvrir Konnaxion Capsule Manager.
3. Importer ou sélectionner une Konnaxion Capsule.
4. Choisir un profil réseau.
5. Créer ou générer le compte admin.
6. Cliquer Démarrer.
7. Obtenir une URL.
```

L’utilisateur ne doit pas configurer :

```text id="hidden-complexity"
Docker
Traefik
PostgreSQL
Redis
Celery
Nginx
certificats
ports internes
.env
migrations
firewall
systemd
```

## 8.2 Écran principal attendu

```text id="main-screen"
Instance: demo-001
État: running
Profil réseau: intranet_private
URL: https://konnaxion.local
Sécurité: PASS
Backup: activé

[Ouvrir Konnaxion]
[Changer profil réseau]
[Créer backup]
[Voir logs]
[Arrêter]
```

---

# 9. Profils réseau produit

Les profils réseau doivent remplacer la configuration manuelle.

```text id="network-profiles"
local_only
intranet_private
private_tunnel
public_temporary
public_vps
offline
```

Le profil par défaut doit être :

```env id="default-profile"
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

Le mode public ne doit jamais être activé par défaut.

---

# 10. Principes de sécurité produit

## 10.1 Private-by-default

Konnaxion doit être privé par défaut.

```text id="private-default"
Aucun service interne exposé.
Aucun port dangereux ouvert.
Aucun mode public sans action explicite.
Aucun secret transporté dans la capsule.
```

## 10.2 Deny-by-default

Le manager doit refuser les configurations dangereuses.

Ports toujours interdits publiquement :

```text id="blocked-ports"
3000  Next.js direct
5000  Django/Gunicorn interne
5432  PostgreSQL
6379  Redis
5555  Flower/dashboard
8000  Django dev/server direct
Docker daemon TCP
```

Les documents de récupération demandent explicitement de ne pas exposer `3000`, `5555`, `5432`, `6379`, `8000` ni Docker daemon, et de limiter l’exposition publique à `80/443` via Traefik. 

## 10.3 Security Gate bloquant

Avant chaque démarrage, Konnaxion Capsule Manager doit valider :

```text id="security-gate"
capsule_signature
image_checksums
manifest_schema
secrets_present
secrets_not_default
firewall_enabled
dangerous_ports_blocked
postgres_not_public
redis_not_public
docker_socket_not_mounted
no_privileged_containers
no_host_network
allowed_images_only
admin_surface_private
backup_configured
```

Un échec critique doit produire :

```text id="security-blocked"
INSTANCE_STATE=security_blocked
```

et empêcher le démarrage.

---

# 11. Architecture applicative visée

Konnaxion v14 doit rester aligné sur sa stack existante :

```text id="canonical-stack"
Frontend: Next.js / React / TypeScript
Backend: Django + Django REST Framework
Database: PostgreSQL
Background jobs: Celery
Broker/result backend: Redis
Reverse proxy: Traefik
Media/static service: Nginx
Runtime cible: Docker Compose
```

La documentation actuelle confirme aussi l’existence de scripts, fichiers Docker Compose, settings Django, routes, modules backend et frontend, ainsi qu’une structure complète de projet Konnaxion. 

---

# 12. Domaines fonctionnels couverts

Konnaxion doit conserver son identité modulaire.

## 12.1 Kollective Intelligence

```text id="domain-kollective"
expertise
réputation
scores pondérés
confiance
vote intelligent
historique d’évolution
```

## 12.2 ethiKos

```text id="domain-ethikos"
débats structurés
positions
arguments
consultations civiques
suivi d’impact
```

## 12.3 KeenKonnect

```text id="domain-keenkonnect"
projets collaboratifs
ressources
tâches
messages
équipes
évaluations
```

## 12.4 KonnectED

```text id="domain-konnected"
ressources éducatives
certifications
évaluations
portfolios
progression
forums
co-création
```

## 12.5 Kreative

```text id="domain-kreative"
œuvres
galeries
archives
traditions
préservation culturelle
expositions
```

Ces domaines sont présents dans les références fonctionnelles et schémas de données v14. 

---

# 13. Cas d’usage prioritaires

## 13.1 Démo locale

```text id="use-case-local-demo"
Un utilisateur démarre Konnaxion sur une machine dédiée.
L’application est accessible seulement sur la machine locale.
Aucun service réseau n’est exposé.
```

## 13.2 Intranet d’organisation

```text id="use-case-intranet"
Une organisation branche une Konnaxion Box sur son réseau local.
Les utilisateurs accèdent à Konnaxion via https://konnaxion.local.
L’instance n’est pas accessible depuis Internet.
```

## 13.3 Démo privée à distance

```text id="use-case-private-tunnel"
Le responsable active un tunnel privé.
Seules les personnes autorisées peuvent accéder à l’instance.
Aucun port routeur n’est ouvert.
```

## 13.4 Démo publique temporaire

```text id="use-case-public-temp"
Le responsable crée un lien public temporaire.
Le lien expire automatiquement.
Le système revient ensuite en mode privé.
```

## 13.5 VPS public contrôlé

```text id="use-case-public-vps"
Une instance publique est déployée sur un VPS propre.
Seuls 80/443 sont publics.
SSH est limité.
Les secrets sont générés ou rotés.
```

---

# 14. Hors scope

Le produit cible ne doit pas viser immédiatement :

```text id="out-of-scope"
Kubernetes
multi-node orchestration
haute disponibilité complète
marketplace de plugins tiers
SaaS multi-tenant public
auto-hébergement non sécurisé
configuration réseau libre sans garde-fous
exposition publique permanente depuis un réseau résidentiel par défaut
```

Kubernetes et autres couches lourdes ne sont pas nécessaires pour le besoin actuel : Konnaxion dispose déjà d’une architecture Docker, Redis, Celery, Traefik et PostgreSQL suffisante pour le modèle capsule/appliance.

---

# 15. MVP produit

Le MVP doit livrer :

```text id="mvp-list"
1. Format .kxcap minimal
2. Manifest signé
3. Import capsule
4. Démarrage Docker Compose
5. Profils réseau local_only, intranet_private, public_temporary
6. Génération automatique des secrets
7. Security Gate bloquant
8. Interface de statut
9. Backup manuel
10. Logs visibles
11. Arrêt propre
12. Documentation opérateur
```

Ne pas inclure dans le MVP :

```text id="not-mvp"
éditeur visuel complet
marketplace
cluster
haute disponibilité
gestion multi-organisation avancée
synchronisation cloud
mises à jour automatiques complexes
```

---

# 16. Critères de succès

## 16.1 Critères plug-and-play

```text id="success-plug-play"
Une personne non DevOps peut démarrer une instance en moins de 10 minutes.
Aucun fichier .env n’est modifié manuellement.
Aucun port interne n’est choisi manuellement.
Aucune commande Docker n’est nécessaire pour l’opérateur.
```

## 16.2 Critères sécurité

```text id="success-security"
Le mode par défaut est privé.
PostgreSQL n’est jamais public.
Redis n’est jamais public.
Docker socket n’est jamais monté dans un conteneur.
Les capsules non signées sont refusées.
Les ports dangereux bloquent le démarrage.
Les secrets sont générés localement.
```

## 16.3 Critères opérationnels

```text id="success-ops"
L’instance peut être démarrée, arrêtée, sauvegardée et restaurée.
Les logs sont consultables.
Les healthchecks sont visibles.
Le système peut revenir à l’état privé après un mode public temporaire.
```

## 16.4 Critères développeur

```text id="success-dev"
Une capsule peut être buildée depuis le code source.
Les images sont exportées.
Le manifest est généré.
La capsule est signée.
La capsule est vérifiable avant import.
```

---

# 17. Décisions produit fixées

```text id="product-decisions"
DECISION-01:
Konnaxion devient une plateforme capsule/appliance, pas seulement une app VPS.

DECISION-02:
Le mode par défaut est privé.

DECISION-03:
La configuration manuelle doit être minimale.

DECISION-04:
La sécurité est intégrée au produit, pas seulement à la documentation.

DECISION-05:
La capsule ne contient jamais les secrets réels.

DECISION-06:
Konnaxion Capsule Manager ne doit pas exposer les services internes.

DECISION-07:
Konnaxion Agent exécute seulement des actions allowlistées.

DECISION-08:
Docker Compose est le runtime cible initial.

DECISION-09:
Traefik est le seul point d’entrée réseau.

DECISION-10:
Les modes publics doivent être explicites, limités et contrôlés.
```

---

# 18. Relation avec les documents existants

Les documents existants restent utiles, mais ils sont reclassés.

## 18.1 Documentation technique v14

Rôle :

```text id="doc-role-v14"
source de vérité sur les modules, modèles, routes, architecture applicative et domaines fonctionnels
```

Référence : documentation technique v14 et inventaire de code. 

## 18.2 Runbooks de déploiement VPS

Rôle :

```text id="doc-role-vps"
historique opérationnel et source des leçons de sécurité
```

Ils ne représentent plus la cible finale du produit. Le déploiement Namecheap actuel/historique était hybride : backend Docker Compose, frontend Node/pnpm, Postgres Docker, Redis Docker et Traefik Docker. 

## 18.3 Runbook frontend

Rôle :

```text id="doc-role-frontend"
référence pour le build Next.js et les contraintes mémoire
```

Le frontend nécessite notamment `NODE_OPTIONS="--max-old-space-size=4096"` dans le flux de build validé. 

## 18.4 Workflow backend

Rôle :

```text id="doc-role-backend"
référence pour rebuild, migrations Django, services Docker et superuser
```

Le workflow backend documente les étapes Docker Compose, `makemigrations`, `migrate`, `ps` et `createsuperuser`. 

---

# 19. Résumé exécutif

```text id="executive-summary"
Konnaxion doit évoluer vers une appliance portable et sécurisée.

Le produit cible est une Konnaxion Capsule ouverte par Konnaxion Capsule Manager,
exécutée par Konnaxion Agent,
sur une Konnaxion Box ou un host compatible,
avec runtime Docker Compose,
Traefik comme seul point d’entrée,
et des profils réseau prédéfinis.

La priorité produit est plug-and-play + private-by-default.
```

---

# 20. Prochaine documentation

Le prochain fichier recommandé est :

```text id="next-doc"
DOC-02_Konnaxion_Capsule_Architecture.md
```

Objectif du DOC-02 :

```text id="doc02-objective"
Décrire précisément les composants de la Konnaxion Capsule,
la séparation capsule/instance,
le cycle build/import/start/update/rollback,
et les responsabilités du Manager, de l’Agent et du runtime Docker.
```
