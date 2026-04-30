---
doc_id: DOC-11
title: Konnaxion Box Appliance Image
project: Konnaxion
app_version: v14
param_version: kx-param-2026.04.30
status: draft
owner: Konnaxion
last_updated: 2026-04-30
depends_on:
  - DOC-00_Konnaxion_Canonical_Variables.md
  - DOC-01_Konnaxion_Product_Vision.md
  - DOC-02_Konnaxion_Capsule_Architecture.md
  - DOC-04_Konnaxion_Manager_Architecture.md
  - DOC-05_Konnaxion_Agent_Security_Model.md
  - DOC-06_Konnaxion_Network_Profiles.md
  - DOC-07_Konnaxion_Security_Gate.md
  - DOC-08_Konnaxion_Runtime_Docker_Compose.md
  - DOC-09_Konnaxion_Backup_Restore_Rollback.md
canonical_terms:
  - Konnaxion Box
  - Konnaxion Capsule
  - Konnaxion Capsule Manager
  - Konnaxion Agent
  - Konnaxion Instance
  - Konnaxion Backup Set
  - Konnaxion Factory Reset
  - KX_*
---

# DOC-11 — Konnaxion Box Appliance Image

# 1. Objectif du document

Ce document définit l’image appliance officielle de **Konnaxion Box**.

Une **Konnaxion Box** est une machine dédiée prête à l’emploi qui démarre Konnaxion avec un minimum de configuration, en mode privé par défaut, avec sécurité intégrée, profils réseau prédéfinis, backups, mises à jour et rollback.

```text id="doc11-purpose"
Konnaxion Box = machine dédiée + image système + Konnaxion Capsule Manager + Konnaxion Agent + runtime Docker sécurisé
```

L’objectif n’est pas seulement d’installer Konnaxion sur Linux. L’objectif est de produire une image système qui transforme un mini PC ou serveur local en appliance plug-and-play.

---

# 2. Positionnement

La Konnaxion Box est destinée à :

```text id="box-targets"
démos locales
intranets d’organisations
laboratoires citoyens
écoles
OBNL
salles de consultation
déploiements semi-autonomes
démos publiques temporaires contrôlées
```

Elle n’est pas conçue comme :

```text id="box-not-targets"
serveur cloud multi-tenant
cluster Kubernetes
NAS généraliste
machine personnelle non dédiée
serveur résidentiel public ouvert par défaut
```

---

# 3. Principe central

La Konnaxion Box doit être :

```text id="box-principles"
plug-and-play
private-by-default
deny-by-default
offline-capable
capsule-driven
recoverable
observable
updatable
factory-resettable
```

L’utilisateur ne doit pas avoir à configurer manuellement :

```text id="operator-should-not-configure"
Docker
Traefik
PostgreSQL
Redis
Celery
Nginx
UFW
systemd
.env
ports internes
certificats
migrations
volumes
```

Konnaxion utilise déjà une stack complète avec backend **Django + DRF + Celery + Redis**, frontend **Next.js/React**, base **PostgreSQL**, et une infrastructure Docker/Traefik/Nginx en production; la Konnaxion Box doit masquer cette complexité derrière une interface appliance. 

---

# 4. Architecture globale

```text id="box-architecture"
┌──────────────────────────────────────────────┐
│                Konnaxion Box                 │
│  Hardware dédié + OS minimal + firewall      │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│         Konnaxion Appliance OS Layer         │
│  updates, users, firewall, services système  │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│        Konnaxion Capsule Manager             │
│  UI locale, onboarding, status, backups      │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│              Konnaxion Agent                 │
│  service privilégié limité et audité         │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│          Docker Compose Runtime              │
│  Traefik + Next.js + Django + DB + workers   │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│             Konnaxion Instance               │
│  données, secrets, logs, backups, médias     │
└──────────────────────────────────────────────┘
```

---

# 5. Éditions de l’image

## 5.1 Édition standard

```text id="standard-edition"
Nom: Konnaxion Box Standard
Base: Ubuntu Server LTS ou Debian stable
Runtime: Docker Engine + Docker Compose
UI: Konnaxion Capsule Manager
Agent: Konnaxion Agent
Usage: démo, intranet, petite organisation
```

## 5.2 Édition développeur

```text id="developer-edition"
Nom: Konnaxion Box Developer
Inclut: outils de debug, logs étendus, shell admin, build tools optionnels
Usage: développement appliance, QA, validation capsules
```

## 5.3 Édition production locale

```text id="local-production-edition"
Nom: Konnaxion Box Local Production
Inclut: sécurité renforcée, logs réduits, backups automatiques, updates contrôlés
Usage: installation durable en intranet
```

Le MVP doit commencer avec **Konnaxion Box Standard**.

---

# 6. Base système recommandée

## 6.1 OS cible

```text id="target-os"
Base OS: Ubuntu Server LTS
Alternative: Debian stable
Architecture: x86_64
Boot mode: UEFI
Filesystem recommandé: ext4 ou btrfs
Runtime containers: Docker Engine
```

## 6.2 Raison du choix

La base doit être :

```text id="os-requirements"
stable
documentée
facile à maintenir
compatible Docker
compatible mini PC
compatible scripts d’installation
compatible firewall local
```

Ne pas utiliser dans le MVP :

```text id="not-os-mvp"
Kubernetes
microK8s
Nomad
Proxmox comme base obligatoire
TrueNAS comme base obligatoire
système immutable complexe
```

Proxmox peut être utilisé par un opérateur avancé pour héberger une VM Konnaxion Box, mais il ne doit pas être requis pour le MVP.

---

# 7. Matériel recommandé

## 7.1 Minimum acceptable

```text id="hardware-minimum"
CPU: 4 cores x86_64
RAM: 8 GB
Disk: SSD 256 GB
Network: Ethernet
USB: 1 port pour recovery/install
```

## 7.2 Recommandé

```text id="hardware-recommended"
CPU: 6-8 cores x86_64
RAM: 16 GB
Disk: NVMe/SSD 512 GB
Network: Ethernet gigabit
Power: petit UPS si installation durable
```

## 7.3 Justification RAM

Le build frontend Next.js validé nécessite `NODE_OPTIONS="--max-old-space-size=4096"` pour éviter les erreurs mémoire sur VPS limité.  Pour une appliance stable, **8 GB** doit être considéré comme minimum réel, et **16 GB** comme cible confortable.

---

# 8. Layout disque canonique

```text id="disk-layout"
/
├── /opt/konnaxion/
│   ├── capsules/
│   ├── instances/
│   ├── manager/
│   ├── agent/
│   ├── releases/
│   ├── shared/
│   └── backups/
├── /var/log/konnaxion/
├── /etc/konnaxion/
└── /var/lib/konnaxion/
```

## 8.1 Répertoires système

| Chemin                      | Rôle                          |
| --------------------------- | ----------------------------- |
| `/opt/konnaxion/capsules/`  | Capsules `.kxcap` importées   |
| `/opt/konnaxion/instances/` | Instances installées          |
| `/opt/konnaxion/manager/`   | UI/Manager                    |
| `/opt/konnaxion/agent/`     | Agent système                 |
| `/opt/konnaxion/backups/`   | Backups locaux                |
| `/etc/konnaxion/`           | Configuration appliance       |
| `/var/log/konnaxion/`       | Logs système Konnaxion        |
| `/var/lib/konnaxion/`       | État interne du Manager/Agent |

## 8.2 Instance type

```text id="instance-layout"
 /opt/konnaxion/instances/<KX_INSTANCE_ID>/
 ├── env/
 ├── postgres/
 ├── redis/
 ├── media/
 ├── logs/
 ├── backups/
 ├── state/
 └── compose/
```

Rappel canonique :

```text id="capsule-instance-rule"
Capsule = application immuable
Instance = données, secrets, logs, médias, backups et état runtime
```

---

# 9. Utilisateurs système

## 9.1 Utilisateurs canoniques

| Utilisateur   | Rôle                          |   Sudo |         Docker |
| ------------- | ----------------------------- | -----: | -------------: |
| `kx-agent`    | exécute Konnaxion Agent       | limité |       contrôlé |
| `kx-runtime`  | propriétaire fichiers runtime |    non |            non |
| `kx-backup`   | tâches backup                 | limité |            non |
| `admin local` | maintenance manuelle          |    oui | non par défaut |

## 9.2 Règle Docker

Ne pas ajouter un utilisateur opérateur au groupe `docker`.

```text id="docker-group-rule"
Les opérations Docker doivent passer par Konnaxion Agent,
pas par un accès Docker libre donné à l’utilisateur.
```

Cette règle vient directement de l’incident précédent : les notes indiquent que l’attaquant a lancé des conteneurs Docker malveillants, ajouté de la persistence cron et utilisé des mécanismes de backdoor; le nouvel environnement doit donc éviter de donner un contrôle Docker libre à un utilisateur de déploiement. 

---

# 10. Services systemd

```text id="systemd-services"
konnaxion-agent.service
konnaxion-manager.service
konnaxion-firewall.service
konnaxion-healthcheck.timer
konnaxion-backup.timer
konnaxion-update.timer
```

## 10.1 `konnaxion-agent.service`

Rôle :

```text id="agent-service-role"
exécuter les opérations privilégiées autorisées
contrôler Docker Compose
appliquer les profils réseau
vérifier les capsules
gérer backups/restores
appliquer Security Gate
```

## 10.2 `konnaxion-manager.service`

Rôle :

```text id="manager-service-role"
servir l’interface locale
afficher l’état de l’instance
démarrer/arrêter via l’Agent
présenter les profils réseau
présenter logs, backups, healthchecks
```

## 10.3 `konnaxion-firewall.service`

Rôle :

```text id="firewall-service-role"
appliquer la politique deny-by-default
ouvrir uniquement les ports autorisés par profil
fermer les ports dangereux
revenir au profil privé après expiration publique
```

---

# 11. Réseau par défaut

## 11.1 Profil de démarrage

```env id="default-network-profile"
KX_NETWORK_PROFILE=intranet_private
KX_EXPOSURE_MODE=private
KX_PUBLIC_MODE_ENABLED=false
```

Le mode public ne doit jamais être activé au premier boot.

## 11.2 Ports autorisés par défaut

En mode `intranet_private` :

```text id="default-allowed-ports"
443/tcp LAN only
80/tcp optional redirect LAN only
```

## 11.3 Ports bloqués par défaut

```text id="default-blocked-ports"
3000/tcp
5000/tcp
5432/tcp
6379/tcp
5555/tcp
8000/tcp
Docker daemon TCP
```

Les documents de sécurité demandent explicitement de ne pas exposer `3000`, `5555`, `5432`, `6379`, `8000` ni le Docker daemon; les utilisateurs doivent passer par Traefik sur `80/443`. 

---

# 12. Profils réseau supportés

```text id="supported-network-profiles"
local_only
intranet_private
private_tunnel
public_temporary
public_vps
offline
```

## 12.1 `local_only`

```text id="profile-local-only"
Usage: démo sur la machine
Exposition: localhost seulement
Public: non
LAN: non
```

## 12.2 `intranet_private`

```text id="profile-intranet-private"
Usage: organisation locale
Exposition: LAN seulement
Public: non
URL cible: https://konnaxion.local
```

## 12.3 `private_tunnel`

```text id="profile-private-tunnel"
Usage: accès distant privé
Exposition: VPN/tailnet seulement
Port routeur: aucun
```

## 12.4 `public_temporary`

```text id="profile-public-temporary"
Usage: démo publique ponctuelle
Exposition: tunnel temporaire
Expiration: obligatoire
Auth: obligatoire
```

## 12.5 `public_vps`

```text id="profile-public-vps"
Usage: instance web publique
Exposition: 80/443 seulement
Contexte: VPS propre ou host durci
Non recommandé depuis réseau résidentiel
```

## 12.6 `offline`

```text id="profile-offline"
Usage: démonstration sans réseau
Exposition: aucune
Fonctions externes: désactivées
```

---

# 13. Premier démarrage

## 13.1 Objectif UX

Le premier démarrage doit rester minimal :

```text id="first-boot-goal"
1. Brancher la machine.
2. Ouvrir Konnaxion Capsule Manager.
3. Choisir ou importer une capsule.
4. Choisir le mode réseau.
5. Générer le compte admin.
6. Démarrer.
```

## 13.2 Écran premier démarrage

```text id="first-boot-screen"
Bienvenue dans Konnaxion Box

[1] Importer une capsule
[2] Choisir le mode réseau
[3] Créer l’admin
[4] Démarrer Konnaxion
```

## 13.3 Configuration demandée

L’utilisateur doit seulement fournir :

```text id="minimal-user-input"
nom de l’instance
mode réseau
mot de passe admin ou génération automatique
option backup activé/désactivé
```

Tout le reste est généré automatiquement.

---

# 14. Génération automatique

Au premier démarrage, l’Agent génère :

```text id="auto-generated-items"
KX_INSTANCE_ID
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
DATABASE_URL interne
certificat local si requis
admin initial
Docker networks
volumes
.env d’instance
profil firewall
```

La capsule ne doit jamais contenir les vrais secrets.

Les notes de récupération indiquent que `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DATABASE_URL`, clés privées, tokens, clés SSH et mots de passe admin doivent être considérés comme secrets sensibles et rotés après exposition. 

---

# 15. Konnaxion Capsule incluse

L’image appliance peut être livrée de deux manières.

## 15.1 Sans capsule préinstallée

```text id="no-preinstalled-capsule"
La Konnaxion Box démarre sur le Manager.
L’utilisateur importe un fichier .kxcap.
```

## 15.2 Avec capsule de démo préinstallée

```text id="preinstalled-demo-capsule"
La Konnaxion Box contient une capsule de démo signée.
L’utilisateur peut démarrer immédiatement.
```

Pour le MVP, privilégier :

```text id="mvp-capsule-choice"
capsule de démo préinstallée + option importer nouvelle capsule
```

---

# 16. Runtime Docker Compose

La Konnaxion Box exécute une **Konnaxion Instance** via Docker Compose.

Services canoniques :

```text id="runtime-services"
traefik
frontend-next
django-api
postgres
redis
celeryworker
celerybeat
flower
media-nginx
```

Le déploiement VPS actuel/historique fonctionne déjà avec backend Docker Compose, frontend Node/pnpm, Postgres Docker, Redis Docker et Traefik Docker; la Konnaxion Box doit converger vers un runtime encore plus cohérent où le frontend est aussi intégré au modèle capsule/runtime. 

---

# 17. Routage runtime

```text id="runtime-routing"
https://<HOST>/          -> frontend-next
https://<HOST>/api/      -> django-api
https://<HOST>/admin/    -> django-api
https://<HOST>/media/    -> media-nginx
```

Règle :

```text id="routing-rule"
Traefik est le seul point d’entrée réseau.
Tous les autres services restent internes.
```

Le routage actuel documenté utilise déjà `/` vers Next.js, `/api/` vers Django, `/admin/` vers Django admin et `/media/` vers le service media. 

---

# 18. Security Gate appliance

Avant chaque démarrage, l’Agent doit exécuter :

```text id="security-gate-checks"
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

Résultats possibles :

```text id="security-statuses"
PASS
WARN
FAIL_BLOCKING
SKIPPED
UNKNOWN
```

Si un contrôle critique retourne `FAIL_BLOCKING` :

```text id="security-blocked-state"
KX_INSTANCE_STATE=security_blocked
```

et l’instance ne démarre pas.

---

# 19. Interface principale

```text id="main-ui"
Konnaxion Box

Instance: demo-001
État: running
Profil réseau: intranet_private
URL: https://konnaxion.local
Sécurité: PASS
Backups: activés
Dernier backup: 2026-04-30 09:00

[Ouvrir Konnaxion]
[Changer mode réseau]
[Créer backup]
[Voir logs]
[Mettre à jour]
[Arrêter]
```

---

# 20. Logs

## 20.1 Logs visibles à l’opérateur

```text id="operator-logs"
état instance
erreurs démarrage
résultat migrations
résultat Security Gate
état backups
état réseau
```

## 20.2 Logs techniques

```text id="technical-logs"
docker compose logs
django logs
frontend logs
traefik logs
postgres health
redis health
celeryworker logs
celerybeat logs
agent logs
```

## 20.3 Règle secrets

```text id="logs-secret-rule"
Les logs ne doivent jamais afficher les secrets.
```

Si un secret apparaît dans les logs, il doit être roté.

---

# 21. Backups

La Konnaxion Box doit fournir des backups utilisables sans terminal, mais elle ne doit jamais sauvegarder ou restaurer l’état système complet d’une machine compromise.

La règle canonique est :

```text id="box-backup-rule"
Backup = données applicatives vérifiées.
Backup ≠ image disque complète.
Backup ≠ état système restaurable aveuglément.
```

## 21.1 Backups locaux

Un backup local doit inclure :

```text id="local-backups"
PostgreSQL logical dump
media/uploads
instance manifest
network profile snapshot
capsule reference
app version
capsule version
redacted env metadata
healthcheck result
backup manifest
checksums
```

Un backup local ne doit jamais inclure :

```text id="local-backups-forbidden"
secrets en clair
image disque complète
/tmp
/dev/shm
crontabs système ou utilisateur
anciens authorized_keys
sudoers
Docker daemon state
Docker socket
conteneurs inconnus
volumes Docker non vérifiés
artefacts de compromission
```

## 21.2 Chemins de backup

Le stockage canonique des backups est global à la Box :

```text id="backup-path-canonical"
 /opt/konnaxion/backups/<KX_INSTANCE_ID>/
```

Le dossier dans l’instance est réservé aux pointeurs, état local ou cache léger :

```text id="backup-path-instance-pointer"
 /opt/konnaxion/instances/<KX_INSTANCE_ID>/backups/
```

Règle :

```text id="backup-path-rule"
Les vrais Backup Sets sont sous /opt/konnaxion/backups/<KX_INSTANCE_ID>/.
Le chemin instance/backups ne doit pas devenir une deuxième source de vérité.
```

## 21.3 Classes de backup

La Konnaxion Box doit supporter les classes suivantes :

```text id="box-backup-classes"
daily
weekly
monthly
pre-update
pre-restore
manual
```

Pour le MVP, seules ces classes sont obligatoires :

```text id="box-backup-mvp-classes"
manual
pre-update
pre-restore
```

## 21.4 Rétention par défaut

```env id="backup-retention"
KX_BACKUP_ENABLED=true
KX_BACKUP_ROOT=/opt/konnaxion/backups
KX_BACKUP_RETENTION_DAYS=14
KX_DAILY_BACKUP_RETENTION_DAYS=14
KX_WEEKLY_BACKUP_RETENTION_WEEKS=8
KX_MONTHLY_BACKUP_RETENTION_MONTHS=12
KX_PRE_UPDATE_BACKUP_RETENTION_COUNT=5
KX_PRE_RESTORE_BACKUP_RETENTION_COUNT=5
```

## 21.5 Avertissement espace disque

La Konnaxion Box doit surveiller l’espace disque avant backup, restore, update et factory reset.

Seuils canoniques :

```env id="backup-disk-thresholds"
KX_MIN_FREE_DISK_GB=20
KX_MIN_FREE_DISK_PERCENT=15
KX_BACKUP_WARN_DISK_PERCENT=25
```

Comportement :

```text id="backup-disk-behavior"
Si espace libre < KX_MIN_FREE_DISK_GB: bloquer backup/update/restore non critiques.
Si espace libre < KX_BACKUP_WARN_DISK_PERCENT: afficher warning.
Si backup pré-update impossible: bloquer update capsule.
Si backup pré-restore impossible: bloquer restore destructif.
```

## 21.6 Export hors machine

La Konnaxion Box doit prévoir l’export hors machine, même si le MVP ne choisit pas encore un fournisseur.

Formats d’export supportés cible :

```text id="backup-export-targets"
USB drive
local network share
manual download from Manager UI
encrypted archive
future offsite provider
```

Règles :

```text id="backup-export-rules"
L’export ne doit pas contenir de secrets en clair.
L’export doit inclure backup-manifest.yaml.
L’export doit inclure checksums.sha256.
L’export doit être vérifiable avant import.
L’export doit rester utilisable en environnement offline/intranet.
```

## 21.7 Backup avant mise à jour

Avant chaque update capsule :

```text id="backup-before-update"
1. vérifier capsule entrante
2. créer Backup Set pre-update
3. vérifier checksums
4. arrêter services write-heavy si nécessaire
5. appliquer nouvelle capsule
6. exécuter migrations
7. exécuter Security Gate
8. exécuter healthchecks
9. rollback si échec
```

Une update capsule sans backup `pre-update` vérifié doit être bloquée, sauf mode explicitement marqué `unsafe-dev`.

---

# 22. Restore

Un restore doit restaurer l’application dans un runtime fiable, pas reconstruire un ancien système potentiellement compromis.

Règle canonique :

```text id="restore-rule"
Restore = trusted capsule + verified Backup Set + generated/current secrets + safe network profile.
```

## 22.1 Restore inclus

Un restore peut restaurer :

```text id="restore-includes"
PostgreSQL
médias/uploads
metadata instance
référence capsule compatible
profil réseau validé
manifest backup
healthcheck metadata
```

## 22.2 Restore exclu

Un restore ne doit pas restaurer aveuglément :

```text id="restore-excludes"
anciens secrets compromis
ancienne configuration firewall dangereuse
ancienne clé SSH
anciens tokens externes
anciens conteneurs inconnus
ancien état Docker daemon
ancienne image disque
/tmp
/dev/shm
crontabs
sudoers
authorized_keys
```

## 22.3 Restore par défaut

Le mode restore le plus sûr pour la Box est :

```text id="restore-default"
restore-new
```

Comportement :

```text id="restore-new-behavior"
1. créer nouvelle instance
2. appliquer profil local_only
3. importer Backup Set vérifié
4. restaurer DB/media
5. générer ou réassocier secrets selon politique
6. exécuter migrations compatibles
7. exécuter Security Gate
8. exécuter healthchecks
9. proposer switch vers intranet_private seulement après PASS
```

## 22.4 Restore après factory reset

Après un factory reset, le Manager doit offrir :

```text id="restore-after-factory-reset"
Importer une capsule .kxcap
Importer un Backup Set vérifié
Restaurer dans une nouvelle instance
Démarrer en local_only
Exécuter Security Gate
Passer en intranet_private seulement après validation
```

Le restore après factory reset ne doit jamais réactiver automatiquement :

```text id="restore-after-reset-never-auto"
public_temporary
public_vps
SSH maintenance
anciens tunnels
anciens ports publics
```

## 22.5 Restore UI minimum

L’interface doit présenter :

```text id="restore-ui-minimum"
backup_id
date création
instance source
version capsule source
taille backup
statut vérification
contenu restauré
profil réseau cible
risques détectés
bouton restore-new recommandé
```

---

# 23. Factory reset

La Konnaxion Box doit supporter un reset usine clair, sécuritaire et non ambigu.

Le reset usine n’est pas un restore. Il remet la Box dans un état connu et privé.

## 23.1 Reset soft

```text id="soft-reset"
Supprime ou désactive l’instance active.
Garde les capsules importées.
Garde les Backup Sets vérifiés.
Réinitialise le profil réseau en intranet_private.
Désactive public mode.
Désactive tunnels.
Conserve logs essentiels de reset.
```

Usage :

```text id="soft-reset-use"
Démo terminée
Instance brisée mais Box saine
Besoin de repartir sans effacer les archives
```

## 23.2 Reset complet

```text id="full-reset"
Supprime instances.
Supprime capsules importées.
Supprime logs applicatifs non essentiels.
Supprime secrets générés.
Désactive tunnels.
Ferme ports publics.
Retourne à l’état premier démarrage.
```

Par défaut, le reset complet doit demander quoi faire avec les Backup Sets :

```text id="full-reset-backup-choice"
[recommandé] exporter les backups avant reset
garder les backups locaux
supprimer les backups locaux
```

Si l’utilisateur choisit de supprimer les backups, l’UI doit exiger une confirmation explicite :

```text id="full-reset-delete-confirmation"
DELETE BACKUPS
```

## 23.3 Reset sécurisé

Le reset sécurisé est utilisé si la Box est suspectée compromise.

```text id="secure-reset"
Efface secrets.
Désactive tunnels.
Ferme ports publics.
Passe en offline ou intranet_private.
Marque les backups locaux comme à vérifier.
Bloque restore direct dans l’instance courante.
Force restore-new depuis capsule fiable.
Exige Security Gate PASS avant réexposition réseau.
```

Le reset sécurisé ne doit pas promettre d’effacer forensiquement tous les blocs disque dans le MVP.

## 23.4 Factory reset et backups

Règle :

```text id="factory-reset-backup-rule"
Aucun reset ne doit supprimer les backups sans confirmation explicite.
Aucun restore post-reset ne doit exposer la Box au public automatiquement.
Aucun Backup Set non vérifié ne doit être restauré après reset.
```

---

# 24. Mises à jour

## 24.1 Types de mises à jour

```text id="update-types"
OS updates
Konnaxion Manager updates
Konnaxion Agent updates
Konnaxion Capsule updates
Security policy updates
```

## 24.2 Politique MVP

Pour le MVP :

```text id="mvp-update-policy"
updates OS semi-automatiques
updates Manager/Agent manuelles
updates Capsule manuelles via import .kxcap
rollback obligatoire
```

## 24.3 Update capsule

```text id="capsule-update-flow"
1. importer nouvelle capsule
2. vérifier signature
3. vérifier compatibilité
4. backup instance
5. arrêter services
6. appliquer nouvelle capsule
7. migrations
8. healthcheck
9. switch
10. rollback si échec
```

Le workflow backend actuel documente déjà les opérations de rebuild, migrations Django, vérification des conteneurs et création de superuser; l’appliance doit automatiser ces étapes via le Manager/Agent. 

---

# 25. États système

## 25.1 États appliance

```text id="box-states"
factory_new
first_boot
configured
ready
running
degraded
updating
recovering
security_blocked
factory_resetting
```

## 25.2 États instance

```text id="instance-states"
created
importing
verifying
ready
starting
running
stopping
stopped
updating
rolling_back
degraded
failed
security_blocked
```

---

# 26. Variables appliance

```env id="box-env"
KX_BOX_ID=<GENERATED_ON_FIRST_BOOT>
KX_BOX_NAME=konnaxion-box
KX_BOX_EDITION=standard
KX_BOX_VERSION=2026.04.30
KX_OS_BASE=ubuntu-lts
KX_AGENT_VERSION=0.1.0
KX_MANAGER_VERSION=0.1.0
KX_DEFAULT_NETWORK_PROFILE=intranet_private
KX_REQUIRE_SIGNED_CAPSULE=true
KX_BACKUP_ENABLED=true
KX_BACKUP_ROOT=/opt/konnaxion/backups
KX_BACKUP_RETENTION_DAYS=14
KX_DAILY_BACKUP_RETENTION_DAYS=14
KX_WEEKLY_BACKUP_RETENTION_WEEKS=8
KX_MONTHLY_BACKUP_RETENTION_MONTHS=12
KX_PRE_UPDATE_BACKUP_RETENTION_COUNT=5
KX_PRE_RESTORE_BACKUP_RETENTION_COUNT=5
KX_MIN_FREE_DISK_GB=20
KX_MIN_FREE_DISK_PERCENT=15
KX_BACKUP_WARN_DISK_PERCENT=25
KX_FACTORY_RESET_KEEP_BACKUPS=true
KX_FACTORY_RESET_REQUIRE_BACKUP_EXPORT_WARNING=true
KX_RESTORE_DEFAULT_MODE=restore-new
KX_RESTORE_DEFAULT_NETWORK_PROFILE=local_only
KX_PUBLIC_MODE_ENABLED=false
```

Ces variables doivent être harmonisées avec `DOC-00_Konnaxion_Canonical_Variables.md` avant d’être considérées comme définitivement canoniques si elles ne sont pas encore présentes dans DOC-00.

---

# 27. Image build pipeline

L’image Konnaxion Box doit être produite par un pipeline reproductible.

```text id="image-build-pipeline"
1. préparer base OS
2. appliquer hardening système
3. installer Docker Engine
4. installer Konnaxion Agent
5. installer Konnaxion Capsule Manager
6. installer firewall policy
7. installer services systemd
8. ajouter capsule de démo optionnelle
9. nettoyer secrets build
10. générer image disque
11. calculer checksum
12. signer image
```

---

# 28. Artefacts produits

```text id="image-artifacts"
konnaxion-box-standard-2026.04.30.img
konnaxion-box-standard-2026.04.30.img.sha256
konnaxion-box-standard-2026.04.30.img.sig
konnaxion-box-standard-2026.04.30.release-notes.md
```

---

# 29. Installation sur machine dédiée

## 29.1 Méthode USB

```text id="usb-install"
1. flasher l’image sur USB
2. booter la machine dédiée
3. installer sur disque interne
4. redémarrer
5. ouvrir Konnaxion Manager
```

## 29.2 Méthode disque préinstallé

```text id="preinstalled-disk"
1. image écrite directement sur SSD/NVMe
2. machine livrée prête
3. premier démarrage lance onboarding
```

## 29.3 Méthode VM

```text id="vm-install"
1. créer VM Ubuntu/Debian compatible
2. installer Konnaxion Box image ou script bootstrap
3. utiliser comme appliance virtuelle
```

---

# 30. Sécurité bootstrapping

Au premier démarrage :

```text id="bootstrap-security"
désactiver mots de passe par défaut
générer KX_BOX_ID
générer secrets instance
forcer changement admin
appliquer firewall
désactiver public mode
désactiver SSH public
vérifier capsules signées
```

## 30.1 SSH

Par défaut :

```text id="ssh-default"
SSH désactivé ou LAN-only.
Aucun accès root SSH.
Aucune authentification par mot de passe en mode production locale.
```

Pour maintenance :

```text id="ssh-maintenance"
activation temporaire
clé SSH seulement
expiration automatique possible
journalisation obligatoire
```

---

# 31. Menaces couvertes

La Konnaxion Box doit réduire les risques suivants :

```text id="covered-threats"
exposition accidentelle de Postgres
exposition accidentelle de Redis
exposition accidentelle de Next.js direct
exposition accidentelle de Flower/dashboard
capsule modifiée
image Docker inconnue
secret par défaut
secret transporté dans capsule
Docker socket monté dans conteneur
conteneur privileged
mode public oublié actif
absence de backup
mauvaise restauration après incident
```

Le déploiement précédent a montré des indicateurs graves : image Docker malveillante `negoroo/amco:123`, conteneurs `amco_*`, miner, `/tmp/sshd`, `/dev/shm/*`, crontab de persistence, tentative de création `pakchoi` et fichier sudoers. 

---

# 32. Hors scope du MVP appliance

```text id="box-mvp-out-of-scope"
haute disponibilité multi-machine
cluster Kubernetes
marketplace publique
multi-tenant SaaS
chiffrement disque avancé avec TPM obligatoire
gestion MDM entreprise
déploiement automatique chez clients externes
support hardware universel
```

---

# 33. MVP Konnaxion Box

Le MVP doit inclure :

```text id="box-mvp"
image Ubuntu/Debian préparée
Docker Engine
Konnaxion Agent
Konnaxion Capsule Manager
import .kxcap
capsule démo optionnelle
profil local_only
profil intranet_private
profil public_temporary
Security Gate
firewall deny-by-default
backup manuel
backup pre-update
backup pre-restore
restore manuel
restore-new recommandé
export backup hors machine
logs opérateur
factory reset avec protection backups
```

Ne pas inclure immédiatement :

```text id="box-mvp-not-include"
auto-update complexe
cluster
VPN propriétaire
haute disponibilité
marketplace
gestion multi-box
monitoring cloud centralisé
```

---

# 34. Critères d’acceptation

## 34.1 Plug-and-play

```text id="acceptance-plug-play"
Une Konnaxion Box neuve démarre jusqu’au Manager.
Un utilisateur peut importer une capsule.
Un utilisateur peut démarrer Konnaxion sans terminal.
Une URL fonctionnelle est affichée.
Aucun .env n’est édité manuellement.
```

## 34.2 Sécurité

```text id="acceptance-security"
Le mode par défaut est privé.
Aucun port dangereux n’est public.
Postgres n’est pas accessible depuis le LAN hors réseau Docker.
Redis n’est pas accessible depuis le LAN hors réseau Docker.
Docker socket n’est pas monté dans les conteneurs.
Les capsules non signées sont refusées.
Les secrets sont générés au premier démarrage.
Le mode public temporaire expire automatiquement.
Un restore post-reset ne réactive pas le mode public automatiquement.
Un Backup Set non vérifié ne peut pas être restauré.
```

## 34.3 Opérations

```text id="acceptance-ops"
Start fonctionne.
Stop fonctionne.
Backup fonctionne.
Backup verify fonctionne.
Restore fonctionne.
Restore-new fonctionne.
Factory reset fonctionne.
Factory reset ne supprime pas les backups sans confirmation explicite.
Export backup hors machine est prévu.
Logs visibles.
Security Gate visible.
Update capsule avec rollback fonctionne.
```

## 34.4 Performance minimale

```text id="acceptance-performance"
La machine démarre le Manager automatiquement.
L’instance Konnaxion atteint l’état running.
Le frontend répond via Traefik.
L’API répond via /api/.
L’admin Django répond via /admin/.
Les workers Celery démarrent.
```

---

# 35. Décisions fixées

```text id="doc11-decisions"
DECISION-11-01:
Konnaxion Box est une appliance dédiée, pas seulement un script d’installation.

DECISION-11-02:
La base MVP est Ubuntu Server LTS ou Debian stable.

DECISION-11-03:
Docker Compose est le runtime initial.

DECISION-11-04:
Le profil réseau par défaut est intranet_private.

DECISION-11-05:
Le mode public est toujours explicite, temporaire ou réservé au profil public_vps.

DECISION-11-06:
L’utilisateur opérateur ne reçoit pas d’accès Docker libre.

DECISION-11-07:
Konnaxion Agent est le seul composant autorisé à appliquer les opérations privilégiées.

DECISION-11-08:
La capsule ne contient aucun secret réel.

DECISION-11-09:
La Konnaxion Box doit supporter backup, restore et factory reset.

DECISION-11-10:
La Konnaxion Box doit être utilisable sans terminal pour le cas standard.

DECISION-11-11:
Le stockage canonique des backups est /opt/konnaxion/backups/<KX_INSTANCE_ID>/.

DECISION-11-12:
Le restore par défaut après reset ou incident est restore-new en profil local_only.

DECISION-11-13:
Aucun factory reset ne supprime les backups sans confirmation explicite.

DECISION-11-14:
Une update capsule doit créer et vérifier un backup pre-update avant modification.
```

---

# 36. Relation avec les autres documents

```text id="doc-relations"
DOC-00:
définit variables et noms canoniques.

DOC-01:
définit la vision produit appliance/capsule.

DOC-02:
décrit la Konnaxion Capsule.

DOC-04:
décrit le Konnaxion Capsule Manager.

DOC-05:
décrit le modèle de sécurité du Konnaxion Agent.

DOC-06:
décrit les profils réseau.

DOC-07:
décrit le Security Gate.

DOC-08:
décrit le runtime Docker Compose.

DOC-09:
décrit backup, restore, rollback, Backup Sets, restore-new, pre-update, pre-restore et règles de récupération après incident.

DOC-10:
décrit le Builder CLI.
```

---

# 37. Résumé exécutif

```text id="doc11-summary"
La Konnaxion Box est l’appliance matérielle/logicielle qui rend Konnaxion plug-and-play.

Elle fournit une base système sécurisée,
un Manager local,
un Agent privilégié contrôlé,
un runtime Docker Compose,
des profils réseau prédéfinis,
des backups vérifiables,
un restore-new sécurisé,
un export backup hors machine,
un reset usine protégé,
et un mode privé par défaut.

Elle transforme Konnaxion d’une application complexe à déployer
en une capsule opérable en local, intranet ou démo temporaire,
sans exposer les services internes.
```

---

# 38. Prochaine documentation recommandée

```text id="next-doc"
DOC-02_Konnaxion_Capsule_Architecture.md
```

ou, si on veut rester dans l’ordre appliance :

```text id="next-appliance-doc"
DOC-05_Konnaxion_Agent_Security_Model.md
```

Le plus logique après DOC-11 est **DOC-05**, parce que la Konnaxion Box dépend fortement du modèle de permissions entre le Manager, l’Agent, Docker, le firewall et le système.
