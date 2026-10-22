# CinetINT, billetterie en ligne du cinéma d'Évry

## Groupe 6

Projet d'architecture web, FISA 2028 (Télécom SudParis, septembre 2026).
Groupe **CinetINT** : [@aztrooow](https://github.com/aztrooow), [@Adurnea](https://github.com/Adurnea), [@eldertek](https://github.com/eldertek).

Version en ligne : **https://fisa.eclipse-technology.eu**

| Page | Adresse |
|---|---|
| Programme et réservation | [/](https://fisa.eclipse-technology.eu/) |
| Borne du hall (mode kiosque) | [/borne](https://fisa.eclipse-technology.eu/borne) |
| Contrôle des billets | [/controle](https://fisa.eclipse-technology.eu/controle) |
| Infos pratiques (accès, horaires, tarifs) | [/infos](https://fisa.eclipse-technology.eu/infos) |
| Espace gérant | [/admin](https://fisa.eclipse-technology.eu/admin) |
| Données de chaque table (gérant) | [/admin/donnees](https://fisa.eclipse-technology.eu/admin/donnees) |
| Données en JSON | [/api/donnees](https://fisa.eclipse-technology.eu/api/donnees) |
| Documentation de l'API | [/api/docs](https://fisa.eclipse-technology.eu/api/docs) |

Documentation technique : [docs/architecture.md](docs/architecture.md) (schéma, technologies, échanges entre services, données, déploiement). Schémas : [base de données](docs/base-de-donnees.svg), [infrastructure Docker](docs/infrastructure-docker.svg). Réponses aux questions du cours : [docs/questions-cours.md](docs/questions-cours.md). Kubernetes (défis, charte Helm, images) : [k8s/README.md](k8s/README.md) et [section 11 bis](#11-bis-kubernetes).

---

## 1. Résumé du besoin

Le cinéma d'Évry exploite **6 salles d'environ 300 places** sur un emplacement très fréquenté. La vente se fait aujourd'hui uniquement sur des **bornes locales** : il n'existe ni système en ligne, ni infrastructure exploitable, et le site actuel ne supporterait pas la charge. On part donc de zéro.

Le gérant a exprimé deux problèmes concrets.

**Les pics d'affluence.** Le week-end, et plus encore lors d'événements comme la Paris Games Week, la file d'attente devant les bornes devient le goulot d'étranglement : le nombre de bornes plafonne le nombre de ventes et des spectateurs repartent sans billet.

**Le manque de pilotage.** Le gérant n'a aucune vue en temps réel sur le remplissage de ses séances, et rien ne garantit qu'un billet présenté à l'entrée est authentique.

La billetterie en ligne répond aux deux : elle sort la vente des bornes (la capacité de vente n'est plus limitée par le matériel) et elle rend le billet contrôlable.

| Objectif métier | Réponse technique |
|---|---|
| Vendre en ligne et absorber les pics | Services sans état, multipliables, verrous de sièges dans Redis |
| Garantir l'authenticité des billets | Billet signé en Ed25519, vérifié au scan |
| Piloter le remplissage | Tableau de bord mis à jour en direct (Server-Sent Events) |
| Gérer une tarification variable | Moteur de règles, aucun tarif écrit dans le code |
| Ne plus dépendre des bornes | La borne devient un client du système parmi d'autres |

### Ce que le client a tranché

| Décision | Conséquence sur la conception |
|---|---|
| **Pas de revente** entre particuliers | Aucun transfert de propriété d'un billet |
| **Pas de modification** de billet | Un changement = remboursement puis nouvel achat. Un seul chemin à tester |
| **Billet non nominatif** mais identifiable | On authentifie le billet, pas le porteur : aucune donnée personnelle |
| **Pas de compte client** | Le billet s'affiche après paiement et se télécharge en PDF ; la commande se retrouve par son lien |
| **Paiement** par le prestataire existant du cinéma | Aucune donnée de carte ne passe par nos services |
| **Remboursement oui**, modification non | Remboursement refusé une fois le billet scanné |
| **Tarif unique** pour un événement (ex. « Terminator grandeur nature ») | Règle de priorité maximale, visible dans l'application avant paiement |

### Acteurs

| Acteur | Besoin principal | Contrainte |
|---|---|---|
| **Spectateur** | Choisir une séance et ses places, payer, recevoir son billet | Depuis n'importe quel écran, sans compte |
| **Borne** | Même parcours d'achat, sur place | Mode kiosque, écran tactile |
| **Contrôleur** | Scanner un billet et avoir un verdict immédiat | Doit continuer à fonctionner si la billetterie tombe |
| **Gérant** | Programmer, fixer les tarifs, suivre le remplissage, rembourser | Accès protégé |

### Exigences non fonctionnelles

| Exigence | Cible | Pourquoi |
|---|---|---|
| **Charge** | environ 1 800 places mises en vente en même temps, pics le week-end | L'ouverture des ventes d'un événement concentre la demande sur quelques minutes |
| **Cohérence** | **aucune double réservation**, même sous forte concurrence | Deux spectateurs sur le même siège, c'est un incident en salle |
| **Performance** | plan de salle en moins de 500 ms, scan en moins de 200 ms | Un scan lent recrée la file d'attente qu'on veut supprimer |
| **Disponibilité** | le contrôle d'entrée continue si la billetterie est injoignable | Une panne ne doit pas bloquer l'entrée d'une salle pleine |
| **Adaptabilité** | mobile, tablette, ordinateur, borne tactile | Demande explicite du client |
| **Sécurité** | billet infalsifiable, aucune donnée de carte stockée | Stocker des cartes imposerait la conformité PCI-DSS au cinéma |

---

## 2. Fonctionnalités

**Spectateur**
- Programme de la semaine, fiche de chaque film avec ses séances par jour.
- Plan de salle mis à jour en direct : un siège réservé par quelqu'un d'autre se grise sans recharger la page.
- Choix de 1 à 10 places, catégorie de tarif par place (plein, étudiant, moins de 14 ans, senior), prix et libellé du tarif affichés avant le paiement.
- Places bloquées 10 minutes pendant le paiement, puis remises en vente automatiquement.
- Billets avec QR code signé, affichés après paiement et téléchargeables en PDF.
- Remboursement en ligne jusqu'à une heure avant la séance, refusé si le billet a déjà été scanné.
- Page « Infos pratiques » (`/infos`) : accès au cinéma, horaires, grille des tarifs lue dans l'API.

**Borne** : la même application en mode kiosque (`/borne`), grands boutons, retour automatique au programme.

**Contrôleur** (`/controle`) : lecture du QR code à la caméra ou saisie du code, verdict plein écran lisible de loin (entrée validée, déjà utilisé, remboursé, faux billet), historique des derniers passages.

**Gérant** (`/admin`)
- Remplissage de chaque séance en direct, chiffres du jour (taux de remplissage, billets vendus, recette, entrées).
- Programmation : ajout et suppression de séances (la salle doit être libre, ménage compris), gestion des films.
- Grille tarifaire : règles, catégories de spectateurs, événements.
- Recherche d'une commande par référence et remboursement.
- Journal du contrôle d'entrée (repasses et faux billets compris).
- Réglages : durée du blocage des places, nombre maximum de places par commande, délai de remboursement.
- Données : une page par table de la base (toutes les lignes, toutes les colonnes, pagination) et le détail d'une ligne, depuis `/admin/donnees`.

**Programmation réelle.** Les films, affiches, synopsis et horaires sont repris chaque heure de la programmation publique du CGR Évry 2, puis répartis sur nos six salles. Si cette source ne répond pas, la programmation en place est conservée ; s'il n'y a plus aucune séance à venir (premier démarrage sans réseau, par exemple), une semaine fictive est générée. Pour que les plans de salle ne soient pas vides à la démonstration, chaque nouvelle séance reçoit des ventes simulées, enregistrées comme des ventes aux bornes.

---

## 3. Architecture principale

Quatre services applicatifs, chacun dans son conteneur, plus PostgreSQL, Redis et un conteneur nginx qui sert de point d'entrée unique.

![Architecture de CinetINT : services, technologies et échanges](docs/architecture.svg)

La [documentation technique](docs/architecture.md) détaille chaque service, les technologies et leurs versions, les échanges pas à pas (diagrammes de séquence), les clés Redis, la sécurité, la configuration et le passage sous Kubernetes.

| Service | Rôle | Port (interne) | Détient |
|---|---|---|---|
| **front** | Rend côté serveur l'accueil, les fiches films et la borne (rapides, lisibles par les moteurs de recherche) ; sert l'application React pour le plan de salle, le paiement, les billets, le contrôle et le back-office | 8080 | rien |
| **back** | API REST de la billetterie : catalogue, verrous de sièges, commandes, paiement, remboursements, back-office, flux temps réel | 8000 | PostgreSQL, Redis |
| **qr-generator** | Signe les billets, dessine les QR codes et le PDF | 8001 | la clé privée |
| **qr-verifier** | Vérifie la signature d'un billet puis demande au back le passage atomique de « valide » à « utilisé » | 8002 | la clé publique seulement |

Le seul port publié est celui du **proxy** nginx (`http://localhost/`), qui répartit le trafic par préfixe d'URL ; les ports des services ne sont joignables que sur les réseaux Docker. Les routes `/internal/...` ne servent qu'entre services (en-tête `X-Service-Token`) et ne sont jamais exposées par le proxy (404).

**Pourquoi séparer la génération et la vérification ?** Le vérificateur ne possède que la clé publique : il peut dire si un billet vient bien de nous, jamais en fabriquer un. Une fuite du poste de contrôle ne permet donc pas d'émettre de faux billets.

**Sans état.** Hors du mode dégradé du vérificateur, aucun service ne garde d'état en mémoire : le personnel s'authentifie par jeton JWT, les verrous de sièges et les compteurs vivent dans Redis, les événements temps réel passent par le pub/sub de Redis. N'importe quelle instance peut traiter n'importe quelle requête, ce qui permet de multiplier les instances du back le week-end.

### Choix techniques

| Composant | Choix | Justification |
|---|---|---|
| Front | Pages catalogue rendues par le serveur (Jinja), application monopage React 19 + React Router pour le reste, Vite | Le catalogue doit s'afficher vite ; le plan de salle doit se mettre à jour sans recharger |
| API | FastAPI (Python 3.13), REST + JSON, Server-Sent Events pour le temps réel | Le temps réel ne sert qu'au plan de salle et au tableau du gérant, le reste reste en REST simple |
| Base | PostgreSQL 17 | Transactions et contrainte d'unicité partielle : c'est elle qui garantit l'absence de double réservation |
| Cache | Redis 8 | Expiration automatique des clés pour les verrous, compteurs atomiques, pub/sub entre instances |
| Signature | Ed25519 (bibliothèque `cryptography`) | Signature courte (64 octets), QR code lisible, vérification sans secret partagé |
| QR et PDF | `segno`, `fpdf2` | Rendu côté serveur, rien à installer chez le spectateur |
| Conteneurs | Docker, un conteneur par service, nginx en proxy, migrations Alembic | Préparation directe au passage sous Kubernetes ; schéma versionné |

### Parcours d'un achat

1. Le spectateur choisit ses places : le back pose un verrou Redis par siège, en une seule opération atomique (script Lua), pour 10 minutes.
2. Le back crée la commande (en attente) et une session chez le prestataire de paiement.
3. Le paiement accepté, le back demande au qr-generator de signer un jeton par billet, enregistre les billets en base, libère les verrous et publie le changement d'état des sièges.
4. Le navigateur affiche les billets ; chaque QR code est dessiné par le qr-generator à partir du jeton signé.

### Parcours d'un contrôle

1. Le contrôleur scanne le QR code : le qr-verifier vérifie la signature Ed25519, sans appel réseau.
2. Si elle est bonne, il demande au back de passer le billet de « valide » à « utilisé » par une seule requête `UPDATE ... WHERE statut = 'valide'`.
3. Un second passage du même billet ne modifie plus aucune ligne : il est refusé (« déjà utilisé »).
4. Si le back ne répond plus, le vérificateur accepte sur la seule signature, refuse une seconde présentation du même billet pendant la panne, et rejoue les passages dès que le back revient.

---

## 4. Modèle de données

Schéma complet de la base (tables, colonnes, types, clés, contraintes d'unicité et de statut, index), généré à partir des modèles SQLAlchemy de `back/app/models.py` :

![Schéma de la base de données de CinetINT](docs/base-de-donnees.svg)

Le schéma est créé par la migration Alembic `back/migrations/versions/0001_schema_initial.py`, produite par `alembic revision --autogenerate` puis relue ; un test vérifie qu'elle reste identique aux modèles. Version simplifiée des relations :

```mermaid
erDiagram
    SALLE ||--o{ SIEGE : contient
    SALLE ||--o{ SEANCE : accueille
    FILM ||--o{ SEANCE : "est projeté"
    EVENEMENT |o--o{ SEANCE : "peut porter"
    SEANCE ||--o{ COMMANDE : "fait l'objet de"
    COMMANDE ||--o{ BILLET : "émet"
    SEANCE ||--o{ BILLET : admet
    SIEGE ||--o{ BILLET : "occupé par"
    BILLET |o--o{ CONTROLE : "passe au"
    EVENEMENT |o--o{ REGLE_TARIFAIRE : "a pour tarif"
    CATEGORIE |o--o{ REGLE_TARIFAIRE : "tarifée par"
```

| Table | Rôle | Colonnes principales |
|---|---|---|
| `salles` | Les 6 salles | nom, capacité |
| `sieges` | Plan de chaque salle | rang, numéro, position x/y, accessible en fauteuil |
| `films` | Films à l'affiche | titre, réalisation, durée, genre, synopsis, type de production (standard, 3D, art et essai), affiche |
| `evenements` | Manifestations à tarif unique | nom, description |
| `seances` | Un film, une salle, un horaire | début, version (VF, VOST), événement éventuel |
| `categories` | Catégories de spectateurs | plein, étudiant, moins de 14 ans, senior |
| `regles_tarifaires` | Grille de prix | libellé, prix, priorité, critères (jours, type de production, catégorie, événement) |
| `commandes` | Un achat | référence, lignes choisies, montant, statut (en attente, payée, expirée, annulée), session du prestataire |
| `billets` | L'entité centrale | séance, siège, tarif et prix payés, statut (valide, utilisé, remboursé), jeton signé |
| `controles` | Journal du contrôle d'entrée | résultat, poste, horodatage |
| `parametres` | Réglages du gérant | durée du verrou, places maximum, délai de remboursement |
| `comptes` | Personnel | identifiant, mot de passe haché (Argon2), rôle |

Le **billet porte son propre statut et le prix réellement payé**. Le contrôle d'entrée n'a besoin de rien d'autre, et un remboursement se calcule sur le billet sans rejouer une grille tarifaire qui a pu changer entre-temps.

La contrainte qui compte : un **index unique partiel** sur `(seance_id, siege_id)` pour les billets `valide` ou `utilise`. Deux billets actifs sur la même place sont impossibles en base, même en cas de bug applicatif ; un billet remboursé libère la place.

---

## 5. Mécanismes clés

### Aucune double réservation

Un siège doit être bloqué **pendant** le paiement, sinon on le vendrait deux fois pendant que le premier acheteur saisit sa carte, mais pas indéfiniment, sinon un panier abandonné retirerait la place de la vente.

- **Le verrou à expiration.** Une clé Redis par siège (`verrou:{seance}:siege`), posée pour tous les sièges d'une commande ou pour aucun, par un script Lua exécuté atomiquement. Si le paiement échoue ou si le spectateur part, la clé expire seule.
- **La contrainte d'unicité en base.** Même si Redis tombe, la base refuse le second billet.

Le cache accélère, la base arbitre. Un test lance 25 réservations simultanées du même siège : une seule réussit.

### Authenticité du billet

Le QR code contient un jeton `CIN1.<contenu>.<signature>` : identifiant du billet, séance, place et date d'émission, signés en Ed25519. Aucune donnée personnelle. Fabriquer un faux billet supposerait de forger la signature sans la clé privée, qui ne quitte jamais le qr-generator. Le qr-generator refuse d'ailleurs de dessiner un QR code pour un jeton qu'il n'a pas signé.

L'**anti-repasse** neutralise la photo du billet envoyée à un ami : les deux présentations sont authentiques, mais la seconde est refusée parce que le billet est déjà « utilisé ».

### Moteur de tarification

Une règle associe des critères (jours de la semaine, type de production, catégorie de spectateur, événement) à un prix et à une priorité. Pour chaque place, le moteur garde les règles qui s'appliquent et retient la plus prioritaire, puis la plus précise. Le jour s'apprécie à l'heure de Paris.

« Terminator grandeur nature » est un **événement à tarif unique** de priorité maximale : il court-circuite la grille habituelle, et le tarif s'affiche avec son libellé avant le paiement. Ajouter un tel événement est une opération de back-office, pas une modification du code.

### Remplissage en temps réel

Un compteur par séance est tenu dans Redis, incrémenté à chaque vente et décrémenté à chaque remboursement ; chaque changement est publié sur un canal Redis. Chaque instance du back garde **une seule** connexion d'abonnement et redistribue les messages aux navigateurs qu'elle sert. Le compteur reste un cache : il se recalcule depuis la base, à la demande du gérant ou dès qu'il manque.

### Remboursement

Le billet passe à « remboursé », le siège redevient vendable, le compteur et le plan de salle sont mis à jour, et le remboursement est demandé au prestataire de paiement. Un billet déjà scanné n'est jamais remboursable. Le spectateur peut rembourser jusqu'à une heure avant la séance (réglable) ; le gérant peut le faire après ce délai.

### Paiement

Le cinéma a déjà un prestataire. Le back passe par une interface (`Prestataire`) avec deux opérations, créer une session de paiement et rembourser. En attendant le branchement du vrai prestataire, `PrestataireSimule` joue son rôle et une page de paiement simulée permet d'accepter ou de refuser. Aucune donnée de carte n'est saisie ni stockée.

---

## 6. Points de terminaison de l'API

La documentation interactive de chaque service est générée par FastAPI : `/api/docs`, `/qr/docs`, `/verification/docs`.

### back, public

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/programme` | Films à l'affiche et séances des prochains jours |
| GET | `/api/films/{id}` | Fiche d'un film et ses séances |
| GET | `/api/seances/{id}` | Détail d'une séance et prix par catégorie |
| GET | `/api/seances/{id}/plan` | État de chaque siège (libre, verrouillé, vendu, dans votre panier) |
| GET | `/api/seances/{id}/flux` | Changements d'état des sièges en direct (SSE) |
| GET | `/api/tarifs` | Grille tarifaire publique |
| GET | `/api/categories` | Catégories de spectateurs proposées |
| POST | `/api/commandes` | Réserve des places (verrous) et crée la commande |
| GET | `/api/commandes/{id}` | Commande, lignes et billets |
| DELETE | `/api/commandes/{id}` | Annule une commande en attente et libère les places |
| POST | `/api/paiement-simule/{session}` | Réponse du prestataire simulé (accepté ou refusé) |
| GET | `/api/commandes/{id}/billets.pdf` | Billets en PDF |
| POST | `/api/billets/{id}/remboursement` | Remboursement par le spectateur |
| POST | `/api/auth/connexion` | Connexion du personnel, renvoie un jeton JWT |
| GET | `/api/sante` | Sonde de disponibilité (base et Redis) |

### back, espace gérant (jeton du gérant)

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/admin/resume` | Chiffres du jour |
| GET | `/api/admin/remplissage` | Remplissage par séance |
| GET | `/api/admin/flux` | Remplissage en direct (SSE) |
| POST | `/api/admin/remplissage/recalcul` | Recalcule les compteurs depuis la base |
| GET, POST, PUT, DELETE | `/api/admin/films` | Films |
| GET, POST, DELETE | `/api/admin/seances` | Séances (contrôle que la salle est libre) |
| GET | `/api/admin/salles` | Salles |
| GET, POST, PUT | `/api/admin/evenements` | Événements |
| GET, POST, PUT, DELETE | `/api/admin/tarifs` | Règles tarifaires |
| GET, PUT | `/api/admin/categories` | Catégories de spectateurs |
| GET, PUT | `/api/admin/parametres` | Réglages de la vente |
| GET | `/api/admin/commandes?reference=` | Recherche d'une commande |
| POST | `/api/admin/billets/{id}/remboursement` | Remboursement par le gérant |
| GET | `/api/admin/controles` | Journal du contrôle d'entrée |

### back, données de chaque table

Une route JSON par table, avec toutes les lignes et toutes les colonnes (`?limite=` et `?decalage=` pour paginer). Les tables du catalogue sont publiques ; commandes, billets, journal du contrôle et comptes exigent le jeton du gérant. Un mot de passe haché n'est jamais renvoyé (la colonne est masquée) et le jeton signé d'un billet est abrégé.

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/donnees` | Les tables disponibles et leur nombre de lignes |
| GET | `/api/donnees/{table}` | Toutes les lignes de la table, avec la description de ses colonnes |
| GET | `/api/donnees/{table}/{cle}` | Une ligne, désignée par sa clé primaire |

Tables publiques : `salles`, `sieges`, `films`, `evenements`, `seances`, `categories`, `regles-tarifaires`, `parametres`. Tables réservées au gérant : `commandes`, `billets`, `controles`, `comptes`.

### qr-generator

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/qr/{jeton}.svg` | Image du QR code d'un billet authentique |
| GET | `/qr/cle-publique` | Clé publique Ed25519 |
| POST | `/internal/signer` | Signe les billets d'une commande (réservé aux services) |
| POST | `/internal/pdf` | Produit le PDF des billets (réservé aux services) |

### qr-verifier

| Méthode | Chemin | Rôle |
|---|---|---|
| POST | `/verification` | Vérifie un billet et enregistre l'entrée (jeton du contrôleur ou du gérant) |
| GET | `/verification/sante` | Sonde de disponibilité, nombre de passages à rejouer |

### Entre services uniquement

| Méthode | Chemin | Rôle |
|---|---|---|
| POST | `/internal/billets/{id}/utiliser` | Passage atomique de « valide » à « utilisé » |
| POST | `/internal/controles` | Journalise un faux billet |

---

## 7. Arbre des URLs

Tout passe par le proxy : `http://localhost/` en local, `https://fisa.eclipse-technology.eu/` en ligne.

### Pages du front (service front)

| URL | Page |
|---|---|
| `/` | Accueil : programme, évènement du samedi, tarifs, navigation |
| `/films/{id}` | Fiche d'un film et ses séances par jour |
| `/infos` | Infos pratiques : accès, horaires, grille des tarifs |
| `/borne` | Borne du hall (mode kiosque) |
| `/seances/{id}`, `/paiement/{id}`, `/commande/{id}` | Plan de salle, paiement, billets (application React) |
| `/controle` | Contrôle des billets (connexion contrôleur ou gérant) |
| `/admin` | Espace gérant : remplissage, programmation, tarifs, billets, contrôles, paramètres (connexion gérant) |
| `/admin/donnees` | Données : accueil de la section, une carte par table avec son nombre de lignes |
| `/admin/donnees/{table}` | Toutes les lignes et toutes les colonnes d'une table, paginées par 50 |
| `/admin/donnees/{table}/{cle}` | Détail d'une ligne, avec un lien vers les lignes qu'elle référence |
| `/sante` | Sonde du front |

Les tables de `/admin/donnees/{table}` : `salles`, `sieges`, `films`, `evenements`, `seances`, `categories`, `regles-tarifaires`, `parametres`, `commandes`, `billets`, `controles`, `comptes`.

### Routes de l'API (service back)

| URL | Contenu |
|---|---|
| `/api/` + `programme`, `films/{id}`, `seances/{id}`, `tarifs`, `categories`, `commandes`... | Routes métier, détaillées à la section 6 |
| `/api/donnees` | Les 12 tables et leur nombre de lignes |
| `/api/donnees/salles`, `/sieges`, `/films`, `/evenements`, `/seances`, `/categories`, `/regles-tarifaires`, `/parametres` | Toutes les lignes en JSON (public) |
| `/api/donnees/commandes`, `/billets`, `/controles`, `/comptes` | Toutes les lignes en JSON (jeton du gérant) |
| `/api/donnees/{table}/{cle}` | Détail d'une ligne en JSON |
| `/api/admin/...` | Back-office (jeton du gérant) |
| `/api/docs` | Documentation interactive (OpenAPI) |
| `/api/sante` | Sonde (base et Redis) |

### Autres services

| URL | Service |
|---|---|
| `/qr/{jeton}.svg`, `/qr/cle-publique`, `/qr/docs`, `/qr/sante` | qr-generator |
| `/verification`, `/verification/docs`, `/verification/sante` | qr-verifier |
| `/internal/...` | 404 au proxy : routes entre services uniquement |

---

## 8. Conteneurisation Docker

![Infrastructure Docker de CinetINT : espaces de noms, cgroups, réseaux, DNS, volumes](docs/infrastructure-docker.svg)

Sept conteneurs (proxy, front, back, qr-generator, qr-verifier, postgres, redis), construits ou tirés par `docker-compose.yml`.

| Point | Mise en oeuvre |
|---|---|
| **Proxy** | `nginx:1.30.5-alpine`, configuration dans `nginx/nginx.conf`, seul port publié : `127.0.0.1:${PROXY_PORT:-80}:80`. Répartition par préfixe d'URL (voir la section 10), tampon désactivé pour le SSE, `/internal` en 404 |
| **Séparation front / back** | Un Dockerfile par service (`front/Dockerfile`, `back/Dockerfile`, `qr-generator/Dockerfile`, `qr-verifier/Dockerfile`), chacun avec sa configuration propre par variables d'environnement. Le front est construit en deux étapes (Node pour compiler l'application React, Python pour la servir) ; chaque service a une étape `tests` |
| **Réseaux** | `front` : le proxy et les quatre services applicatifs. `back` : le back, PostgreSQL et Redis. La base et Redis ne sont joignables que par le back |
| **DNS interne** | Les services s'adressent par leur nom (`http://back:8000`, `postgres:5432`), résolus par le DNS de Docker (127.0.0.11) |
| **Base de données** | Conteneur `postgres:17-alpine`, volume nommé `postgres`, accessible au seul back |
| **Migrations** | Alembic (`back/alembic.ini`, `back/migrations/`) : `back/entrypoint.sh` lance `alembic upgrade head` au démarrage du conteneur back, sous verrou consultatif PostgreSQL (plusieurs répliques sans conflit) |
| **Fixtures** | `python -m app.fixtures`, lancé juste après les migrations : salles et sièges, catégories, règles tarifaires, évènement, réglages, comptes du personnel. Idempotent : relancé, il ne crée aucun doublon |
| **Santé et ordre de démarrage** | `healthcheck` sur chaque conteneur ; `depends_on` avec `service_healthy` : le back attend la base et Redis, le proxy attend les quatre services |
| **Limites de ressources** | CPU et mémoire plafonnés par service (cgroups, `deploy.resources.limits`) |
| **Volumes** | `postgres` (données de la base), `cles` (clé privée du qr-generator), `nginx.conf` monté en lecture seule dans le proxy |

Réponses aux questions du cours (Dockerfile, compose, variables d'environnement, DNS, migrations, parcours d'une requête) : [docs/questions-cours.md](docs/questions-cours.md).

---

## 9. Lancer le projet

Prérequis : Docker et Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Tout est ensuite joignable par le proxy, sur **http://localhost/** :

| Adresse | Contenu |
|---|---|
| http://localhost/ | Site (programme et réservation) |
| http://localhost/infos | Infos pratiques |
| http://localhost/admin | Espace gérant |
| http://localhost/admin/donnees | Une page par table de la base |
| http://localhost/api/donnees | Les mêmes données en JSON |
| http://localhost/api/docs | Documentation de l'API |
| http://localhost/qr/docs | Documentation de la génération des billets |
| http://localhost/verification/docs | Documentation de la vérification |

Le port 80 est publié sur 127.0.0.1 seulement. S'il est déjà pris sur la machine, choisir un autre port avec `PROXY_PORT` dans `.env` (par exemple `PROXY_PORT=8080`, puis http://localhost:8080/).

Comptes du personnel en local : `gerant` / `gerant` et `controleur` / `controleur` (à changer dans `.env`).

Au premier lancement, le conteneur back crée le schéma (migrations), charge les fixtures puis importe la programmation du CGR (quelques secondes) ; le proxy n'ouvre le port qu'une fois les quatre services « healthy ».

Pour déboguer un service seul (curl, documentation interactive), `docker-compose.debug.yml` publie en plus chaque service sur l'hôte :

```bash
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d
```

Tests (base et Redis de test lancés par Compose) :

```bash
docker compose --profile tests run --rm back-tests
docker compose --profile tests run --rm qr-generator-tests
docker compose --profile tests run --rm qr-verifier-tests
docker compose --profile tests run --rm front-tests
```

Ils couvrent le moteur de tarification, la course de 25 acheteurs sur un même siège, la contrainte d'unicité en base, l'expiration d'une commande, le contrôle à usage unique, le refus de remboursement après scan, la signature et la falsification des billets, le mode dégradé du vérificateur, l'import de la programmation, les migrations (schéma identique aux modèles, base antérieure reconnue), le chargement idempotent des fixtures, les routes de données et les pages du front (infos pratiques).

---

## 10. Déploiement

La version en ligne tourne avec le même `docker-compose.yml`. Le conteneur nginx du dépôt (`nginx/nginx.conf`) répartit le trafic par préfixe, comme le fera l'Ingress Kubernetes. En production, un nginx en frontal sert en plus HTTPS et route de la même manière vers les ports de l'hôte :

| Préfixe | Service |
|---|---|
| `/` | front |
| `/api` | back (tampon désactivé pour les flux SSE) |
| `/qr` | qr-generator |
| `/verification` | qr-verifier |
| `/internal` | jamais exposé (404) |

Les variables `URL_API`, `URL_QR` et `URL_VERIFICATION` restent vides (c'est la valeur par défaut) : le navigateur appelle tout sur le même domaine.

Sur le serveur, le port 80 appartient déjà au nginx de l'hôte : le fichier `.env` y fixe `PROXY_PORT` à un port libre (le conteneur proxy est alors joignable en local sur ce port). Le nginx de l'hôte peut soit viser ce port unique, soit continuer de router par préfixe vers les ports des services si l'on ajoute `docker-compose.debug.yml` (`COMPOSE_FILE=docker-compose.yml:docker-compose.debug.yml`).

---

## 11. Plan d'action

| Étape | Contenu | État |
|---|---|---|
| Recueil du besoin | Entretien avec le gérant, décisions ci-dessus, spécification | fait |
| Implémentation | Les quatre services, la base, les tests, un conteneur par service | fait |
| Mise en ligne | Docker Compose derrière nginx sur fisa.eclipse-technology.eu | fait |
| Kubernetes | Défis 1 à 20 (sauf 17), charte Helm, intégration continue : voir ci-dessous | prêt, à déployer sur le cluster du cours |

## 11 bis. Kubernetes

Tout le travail Kubernetes est dans [`k8s/`](k8s/README.md) : un dossier par défi du [sujet](https://github.com/DF-Telecom-SudParis/CSC8567-Final) (manifests ou commandes, schéma d'infrastructure, réponses aux questions), la charte Helm [`k8s/helm/cinetint`](k8s/helm/cinetint) et les scripts d'images, d'application et de rendu. Chaque défi a été vérifié sur un cluster local (kind, un nœud maître et deux nœuds de travail) ; les preuves sont dans la section « Vérifié sur cluster local » de chaque `reponses.md`.

Images publiques (registre GitHub, téléchargeables sans compte) :

| Image | Versions | Adresse |
|---|---|---|
| front | v1, v2 (page Infos pratiques, défi 8) | [ghcr.io/eldertek/cinetint-front](https://github.com/users/eldertek/packages/container/package/cinetint-front) |
| back | v1, v2, v3 (migration sans interruption, défi 20) | [ghcr.io/eldertek/cinetint-back](https://github.com/users/eldertek/packages/container/package/cinetint-back) |
| qr-generator | v1, v2 | [ghcr.io/eldertek/cinetint-qr-generator](https://github.com/users/eldertek/packages/container/package/cinetint-qr-generator) |
| qr-verifier | v1, v2 | [ghcr.io/eldertek/cinetint-qr-verifier](https://github.com/users/eldertek/packages/container/package/cinetint-qr-verifier) |

| Défi | Contenu |
|---|---|
| [1](k8s/defi1) | Premier Pod, `port-forward` |
| [2](k8s/defi2) | Deployment de 3 répliques, Service ClusterIP, `kubectl proxy`, ressources |
| [3](k8s/defi3) | Site (Pod front + back) et base PostgreSQL dans deux Deployments |
| [4](k8s/defi4) | Ingress vers `django.<groupe>.csc8567.luxbulb.org` |
| [5](k8s/defi5) | Infrastructure complète : front, back, QR, Redis, PostgreSQL, Ingress |
| [6](k8s/defi6) | Charte Helm, ConfigMap de connexion à la base |
| [7](k8s/defi7) | PostgreSQL en StatefulSet, volume persistant, service headless |
| [8](k8s/defi8) | Mise à jour progressive (Rolling Update) v1 vers v2 sans erreur |
| [9](k8s/defi9) | Mise à l'échelle automatique (HPA, 60 % CPU, 10 Pods au plus) |
| [10](k8s/defi10) | Sondes liveness, readiness et startup adaptées à chaque conteneur |
| [11](k8s/defi11) | NetworkPolicy : seul le back joint la base |
| [12](k8s/defi12) | PostgreSQL maître / réplique en réplication en flux, écrit à la main |
| [13](k8s/defi13) | Bonus : la réplication en sous-charte Helm |
| [14](k8s/defi14) | Bonus : Redis (verrous de sièges, temps réel) |
| [15](k8s/defi15) | Bonus : hooks Helm (ConfigMap, sauvegardes avant et après mise à jour) |
| [16](k8s/defi16) | Bonus : sauvegarde planifiée (CronJob) et restauration |
| [18](k8s/defi18) | Bonus : durcissement (non root, lecture seule, limites de débit) |
| [19](k8s/defi19) | Bonus : intégration continue ([workflow](.github/workflows/ci.yml)) |
| [20](k8s/defi20) | Bonus : migration de la base sans interruption (expand / contract) |

Le démarrage de plusieurs répliques du back en même temps est prévu : les migrations Alembic, le chargement des fixtures et l'import de la programmation sont protégés par un verrou consultatif PostgreSQL. Démarrage sur le cluster du cours, ordre d'application et commandes de démonstration : [k8s/README.md](k8s/README.md).

---

## 12. Points ouverts avec le client

Valeurs retenues par défaut, toutes réglables par le gérant sans redéploiement :

- **Délai de remboursement** : jusqu'à 60 minutes avant la séance, sans frais.
- **Places par commande** : 10 au maximum.
- **Durée du blocage pendant le paiement** : 10 minutes.
- **Catégories de spectateurs** : plein tarif, étudiant, moins de 14 ans, senior ; d'autres s'ajoutent depuis le back-office.

Reste à trancher avec le gérant : la conduite à tenir quand une double entrée est découverte après une panne du contrôle (aujourd'hui, elle est journalisée).

---

Programmation, affiches et synopsis : programmation publique du CGR Évry 2 (données AlloCiné), reprise pour la démonstration. Photos de salle : Felix Mooneeram et Kilyan Sockalingum, via Unsplash.
