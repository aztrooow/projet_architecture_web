# Billetterie en ligne — Cinéma d'Évry

Projet d'architecture web. Conception d'un système de billetterie pour un cinéma indépendant de 6 salles.

---

## 1. Contexte

Le cinéma d'Évry exploite **6 salles d'environ 300 places** sur un emplacement très fréquenté. La vente se fait aujourd'hui uniquement sur des **bornes locales** : il n'existe ni système en ligne, ni infrastructure exploitable. Le site actuel ne supporterait pas la charge. On part donc de zéro.

Le gérant a exprimé deux problèmes concrets.

**Les pics d'affluence.** Le week-end, et davantage encore lors d'événements comme la Paris Games Week, la file d'attente devant les bornes devient le goulot d'étranglement : le nombre de bornes plafonne le nombre de ventes, et des spectateurs repartent sans billet. La fréquentation augmente, le problème s'aggrave.

**Le manque de pilotage.** Le gérant n'a aucune vue en temps réel sur le taux de remplissage de ses séances, et rien ne garantit qu'un billet présenté à l'entrée est authentique.

La billetterie en ligne répond aux deux : elle déplace la vente hors des bornes — la capacité de vente n'est plus limitée par le matériel physique — et elle rend le billet contrôlable.

---

## 2. Objectifs

| Objectif métier | Réponse technique |
|---|---|
| Vendre en ligne et absorber les pics | Application web publique, dimensionnée pour la charge |
| Garantir l'authenticité des billets | Billet signé cryptographiquement, vérifié au scan |
| Piloter le remplissage | Tableau de bord temps réel par séance et par salle |
| Gérer une tarification variable | Moteur de tarification à règles, sans tarif codé en dur |
| Ne plus dépendre des bornes | Les bornes deviennent un client du système parmi d'autres |

---

## 3. Périmètre

### Dans le périmètre

- Catalogue des films et des séances
- Plan de salle et **choix des places** par le spectateur
- Paiement en ligne, délégué au **prestataire de paiement existant** du cinéma
- Émission d'un billet électronique **identifiable et vérifiable**
- Contrôle du billet à l'entrée par scan
- Annulation et remboursement
- Tarification multiple : jour, type de production, catégorie de client, plus un tarif dédié à un événement spécifique
- Back-office gérant : programmation, tarifs, suivi du remplissage
- Interface adaptée à tous les formats d'écran : mobile, tablette, ordinateur, borne tactile

### Hors périmètre — décisions explicites du client

Ces exclusions ne sont pas des oublis : elles ont été tranchées par le gérant et **simplifient l'architecture**, ce qui justifie de les rappeler.

| Exclusion | Conséquence sur la conception |
|---|---|
| **Pas de revente** entre particuliers | Aucun transfert de propriété d'un billet, donc pas de place de marché ni d'historique de cession |
| **Pas de modification** de billet | Un changement = annulation + remboursement + nouvel achat. Un seul chemin à implémenter et à tester |
| **Billet non nominatif** | Aucune identité rattachée au billet : moins de données personnelles à protéger, contrainte RGPD allégée |
| **Pas de partenaire tiers** à intégrer | Aucune API externe hors le prestataire de paiement : pas de synchronisation de stock avec un revendeur |

**Point important :** « non nominatif » n'est pas « non contrôlable ». Le client demande un billet *identifiable* — on doit pouvoir prouver qu'il a bien été émis par le système et qu'il n'a pas déjà servi — mais *pas rattaché à une identité*. C'est ce qui oriente le mécanisme décrit en §7.2 : on authentifie **le billet**, pas **le porteur**.

---

## 4. Acteurs

| Acteur | Rôle | Besoin principal | Contrainte propre |
|---|---|---|---|
| **Spectateur** | Achète en ligne | Choisir une séance et ses places, payer, recevoir son billet | Depuis n'importe quel écran, sans compte obligatoire |
| **Borne** | Vend sur place | Même parcours d'achat | Mode kiosque, paiement par carte physique |
| **Contrôleur** | Filtre l'entrée | Scanner un billet, verdict immédiat | Doit fonctionner même si le réseau tombe |
| **Gérant** | Exploite | Programmer les séances, fixer les tarifs, suivre le remplissage, rembourser | Accès protégé, back-office |

---

## 5. Exigences

### 5.1 Fonctionnelles

1. Consulter la programmation et les séances.
2. Sélectionner ses places sur un plan de salle affichant l'état réel de chaque siège.
3. Réserver temporairement les places pendant le paiement, avec expiration automatique.
4. Payer en ligne via le prestataire de paiement du cinéma.
5. Recevoir un billet électronique porteur d'un QR code signé.
6. Contrôler un billet à l'entrée : authenticité **et** usage unique.
7. Appliquer automatiquement la grille tarifaire correspondante.
8. Visualiser le taux de remplissage par séance, en temps réel.
9. Annuler un billet et déclencher son remboursement.
10. Administrer films, séances, salles et tarifs.
11. Définir un tarif exceptionnel pour un événement particulier.

### 5.2 Non fonctionnelles

| Exigence | Cible | Pourquoi |
|---|---|---|
| **Charge** | ~1 800 places mises en vente simultanément (6 × 300) ; pics week-end et événements | L'ouverture des ventes d'un événement concentre la demande sur quelques minutes |
| **Performance** | Plan de salle affiché en moins de 500 ms ; validation d'un scan en moins de 200 ms | Un plan lent fait abandonner l'achat ; un scan lent recrée la file d'attente qu'on supprime |
| **Cohérence** | **Aucun double-booking**, jamais, même sous forte concurrence | Deux spectateurs sur le même siège = incident en salle, impossible à rattraper |
| **Disponibilité** | Le contrôle d'entrée reste opérationnel même réseau coupé | Une panne réseau ne doit pas bloquer l'entrée d'une salle pleine |
| **Adaptabilité** | Tous formats : mobile, tablette, ordinateur, borne tactile | Demande explicite du client |
| **Sécurité** | Billet infalsifiable ; **aucune donnée de carte stockée** | La falsification est une perte sèche ; stocker des cartes ferait porter au cinéma une conformité PCI-DSS inutile |
| **RGPD** | Données personnelles minimales | Cohérent avec le billet non nominatif : seul un e-mail de livraison est nécessaire |

---

## 6. Architecture générale

### 6.1 Vue d'ensemble

Le système s'organise en quatre couches.

**Les clients.** Trois interfaces distinctes s'appuient sur la même API. L'**application web publique** sert le catalogue et le parcours d'achat, sur tous les écrans. La **borne** est cette même application en mode kiosque plein écran : un seul code à maintenir, un seul parcours à corriger. L'**application de scan** du contrôleur est séparée, parce que son besoin est différent : elle doit fonctionner hors ligne.

**L'API.** Une application serveur **sans état**, exposant une API REST/JSON. Sans état signifie qu'aucune information de session n'est conservée dans la mémoire d'une instance : n'importe quelle instance peut traiter n'importe quelle requête. C'est ce qui permet d'en démarrer plusieurs en parallèle le week-end et de les arrêter en semaine.

**Les données.** Une base **PostgreSQL** détient la vérité : films, séances, salles, sièges, billets, règles tarifaires. Un cache **Redis** porte les données à durée de vie courte : réservations temporaires et compteurs de remplissage.

**L'asynchrone.** Une file de messages traite ce qui ne doit pas bloquer la réponse HTTP : envoi des billets par e-mail, appels de remboursement au prestataire de paiement.

Le sens de circulation est simple : les trois clients ne parlent qu'à l'API ; l'API seule accède à PostgreSQL, à Redis et à la file ; le prestataire de paiement n'est joint que par l'API et par la file. Aucun client ne touche directement une donnée.

### 6.2 Choix techniques et justification

| Composant | Choix | Justification | Alternative écartée |
|---|---|---|---|
| **Front public** | Application monopage (React ou Vue), pages catalogue rendues côté serveur | Le plan de salle est très interactif et doit se mettre à jour sans recharger ; le catalogue, lui, doit être rapide et référençable par les moteurs de recherche | Tout rendre côté serveur : plan de salle trop lourd à rafraîchir |
| **Front borne** | Même application, mode kiosque | Un seul code, une seule correction de bug | Application native dédiée : deux bases de code pour un parcours identique |
| **App de scan** | Application installable avec cache local | Seule façon de tenir l'exigence de fonctionnement hors ligne | Page web classique : inutilisable dès que le réseau tombe |
| **API** | REST + JSON, plus une liaison temps réel pour le plan de salle | REST suffit pour le catalogue et l'achat ; seul l'état des sièges a besoin d'être poussé au client au fil de l'eau | Tout en temps réel : complexité inutile sur des données qui bougent peu |
| **Base** | PostgreSQL | Relationnel, transactionnel, contraintes d'unicité fiables — c'est le socle de la garantie anti double-booking (§7.1) | Base non relationnelle : cohérence forte plus difficile à obtenir, précisément là où elle est vitale |
| **Cache** | Redis | Expiration automatique des clés, exactement ce qu'exige une réservation temporaire ; compteurs atomiques pour le remplissage | Gérer les expirations en base : une tâche de nettoyage périodique, plus fragile |
| **Asynchrone** | File de messages | Un e-mail lent ou un prestataire indisponible ne doit pas faire échouer un achat déjà payé | Traitement synchrone : le spectateur attend, et une panne externe casse l'achat |
| **Déploiement** | Conteneurs, instances API multipliables | Permet d'ajuster la capacité aux pics du week-end sans surdimensionner la semaine | Serveur unique : soit trop petit le samedi, soit payé pour rien le mardi |

### 6.3 Modèle de données — entités principales

| Entité | Rôle |
|---|---|
| **Film** | Titre, durée, type de production (utilisé par la tarification) |
| **Salle** | Capacité, plan des sièges |
| **Siège** | Rattaché à une salle, position sur le plan |
| **Séance** | Un film, une salle, une date et heure ; éventuellement rattachée à un événement |
| **Événement** | Manifestation particulière portant un tarif unique |
| **Billet** | Une séance, un siège, un prix payé, un statut, une signature |
| **Règle tarifaire** | Critères d'application et priorité |

Le **billet** est l'entité centrale. Il porte **son propre statut** (`valide`, `utilisé`, `remboursé`) et **le prix effectivement payé**. Cette autonomie est délibérée : le contrôle à l'entrée n'a besoin de rien d'autre que le billet, et le montant d'un remboursement se lit sur le billet sans avoir à rejouer la grille tarifaire, qui aura peut-être changé entre-temps.

---

## 7. Mécanismes clés

Quatre mécanismes portent les exigences les plus délicates.

### 7.1 Anti double-booking

C'est le risque numéro un. Deux spectateurs cliquent sur le même siège à la même seconde ; à l'ouverture des ventes d'un événement, cela n'a rien d'improbable. Le système doit en refuser un, toujours, sans exception.

La difficulté est qu'un siège doit être bloqué **pendant** le paiement — sinon on le vendrait deux fois pendant que le premier acheteur saisit sa carte — mais pas indéfiniment, sinon un panier abandonné retirerait la place de la vente pour toujours.

Deux garde-fous complémentaires répondent à ces deux besoins.

**Le verrou à expiration.** Au moment où le spectateur valide ses places, une clé Redis est posée par siège, avec une durée de vie de quelques minutes. Tant qu'elle existe, le siège apparaît indisponible aux autres clients. Si le paiement aboutit, le billet est créé ; s'il échoue ou si le spectateur abandonne, **la clé expire d'elle-même** et le siège redevient vendable, sans intervention.

**La contrainte d'unicité en base.** Une contrainte sur le couple *(séance, siège)* rend physiquement impossible l'existence de deux billets valides pour la même place. Même si le cache tombe, même en cas de bug applicatif, la base refuse l'écriture.

Le partage des rôles est le point à retenir : **le cache accélère, la base arbitre.** Le verrou évite d'aller solliciter la base pour rien et donne un affichage juste ; la contrainte, elle, est la garantie qui ne peut pas être contournée.

### 7.2 Authenticité du billet

L'exigence est double et apparemment contradictoire : le billet doit être **non nominatif** — donc sans identité — et pourtant **infalsifiable**.

La réponse est de faire porter la preuve par le billet lui-même. Son QR code contient un identifiant et une **signature cryptographique**, calculée par le serveur avec une clé secrète (HMAC-SHA256, ou signature asymétrique si l'on veut que les scanners vérifient sans détenir le secret). Fabriquer un faux billet supposerait de forger cette signature sans la clé : hors de portée.

Le contrôle à l'entrée se fait en deux temps, et cette séparation est ce qui permet le mode dégradé.

1. **Vérification de la signature.** Purement mathématique, elle ne nécessite aucun accès au serveur. Elle répond à : « ce billet a-t-il bien été émis par nous ? »
2. **Vérification du statut.** Le billet passe de `valide` à `utilisé` de façon atomique. Une seconde présentation du même QR code est refusée. C'est l'**anti-repasse**, qui neutralise le cas de la photo du billet envoyée à un ami : les deux billets sont authentiques, mais le second arrivé est rejeté.

**Mode dégradé.** Si le réseau tombe, le scanner ne peut plus consulter le statut. Il accepte alors sur la seule signature — les faux restent bloqués — et journalise localement chaque scan. À la reconnexion, la synchronisation remonte les éventuelles doubles entrées. On accepte ce risque résiduel en connaissance de cause : bloquer l'entrée d'une salle pleine coûterait plus cher qu'une poignée de repasses détectées après coup.

### 7.3 Moteur de tarification

Aucun tarif n'est écrit en dur dans le code : le client demande plusieurs grilles et devra en créer d'autres, sans redéploiement.

Une **règle tarifaire** associe des critères — jour de la semaine, type de production, catégorie de client — à un prix et à une **priorité**. Au moment de l'achat, le moteur retient toutes les règles applicables et **conserve la plus prioritaire**.

Le cas *« Terminator grandeur nature »* se traite alors sans exception dans le code : c'est un **événement à tarif unique**, de priorité maximale, qui court-circuite toute la grille ordinaire. Ajouter un tel événement est une opération de back-office, pas une modification de programme.

Deux règles d'usage complètent le mécanisme. Le tarif appliqué est **affiché au spectateur avant le paiement**, avec son libellé — le client a demandé que la majoration d'un événement soit visible dans l'application. Et il est **enregistré sur le billet** : c'est ce qui permet de rembourser le montant réellement payé, même si la grille a changé depuis.

### 7.4 Taux de remplissage

Le gérant veut une vue en temps réel. Recompter les billets d'une séance à chaque affichage du tableau de bord fonctionnerait, mais sollicite la base sans nécessité.

Un **compteur par séance** est donc tenu dans Redis et incrémenté à chaque émission de billet, décrémenté à chaque remboursement. Le back-office affiche places vendues, places disponibles et pourcentage de remplissage, sur toutes les séances à venir.

Le compteur reste un **cache** : la vérité est le nombre de billets en base. Il peut être recalculé à tout moment à partir de celle-ci, ce qui évite qu'une incohérence devienne définitive.

### 7.5 Remboursement

Trois effets, dans cet ordre : le billet passe au statut `remboursé`, le siège est libéré et redevient vendable, et la demande de remboursement est transmise au prestataire de paiement **de façon asynchrone**. Le spectateur reçoit une confirmation immédiate ; l'appel externe est réessayé en cas d'échec sans bloquer quoi que ce soit.

Une règle métier verrouille le mécanisme : **un billet déjà scanné ne peut plus être remboursé.** Le statut `utilisé` est définitif, ce qui interdit de se faire rembourser une séance déjà vue.

---

## 8. Points à valider avec le client

Quelques zones n'ont pas été tranchées lors du recueil du besoin et doivent l'être avant le développement.

- **Délai limite de remboursement** : jusqu'au début de la séance, ou 24 h avant ? Des frais sont-ils retenus ?
- **Nombre maximum de places par commande** : sans plafond, un seul acheteur peut réserver une salle entière.
- **Durée du verrou de réservation** : trop courte, elle fait échouer des paiements en cours ; trop longue, elle retire des places de la vente pendant les pics.
- **Catégories de clients** à ouvrir dès la mise en service : tarif réduit, étudiant, enfant, abonné ?
- **Conduite à tenir sur une double entrée détectée** après synchronisation d'un scan hors ligne.
