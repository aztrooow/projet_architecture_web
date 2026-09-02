# Billetterie - Cinéma d'Évry

Projet d'architecture web. Conception d'un système de billetterie en ligne pour un cinéma indépendant de 6 salles.

## 1. Contexte

Le cinéma d'Évry exploite 6 salles (environ 300 places par salle en moyenne) sur un emplacement très fréquenté. La vente se fait aujourd'hui uniquement sur des bornes locales : aucun système en ligne, aucune infrastructure existante. Le site actuel ne supporterait pas la charge.

Deux problèmes concrets :

- **Les pics d'affluence.** Le week-end et lors d'événements type Paris Games Week, la file d'attente aux bornes devient le goulot d'étranglement.
- **Le manque de pilotage.** Le gérant n'a pas de vue sur le taux de remplissage, et rien ne garantit qu'un billet présenté à l'entrée est authentique.

## 2. Objectifs

| Objectif | Solution technique |
| -|-|
| Vendre en ligne, absorber les pics | Application web publique, scalable horizontalement |
| Garantir l'authenticité des billets | Billet signé cryptographiquement, contrôlé au scan |
| Piloter le remplissage | Tableau de bord temps réel par séance / salle |
| Gérer une tarification variable | Moteur de tarification à règles |
| Ne plus dépendre des bornes | Les bornes deviennent un client parmi d'autres |

## 3. Périmètre

### Dans le périmètre

- Catalogue des films et des séances, plan de salle
- Choix des places par le spectateur
- Paiement en ligne via un prestataire de paiement existant
- Émission d'un billet électronique **identifiable et vérifiable**
- Contrôle du billet à l'entrée par scan
- Remboursement / annulation
- Tarification multiple : jour, type de production, catégorie de client, et tarif unique dédié à un événement spécifique
- Back-office gérant : programmation, tarifs, taux de remplissage
- Responsiv : mobile, tablette, desktop, bornes

### Hors périmètre (décisions explicites du client)

- **Pas de revente** entre particuliers
- **Pas de modification** de billet (l'annulation-remboursement puis un rachat remplace la modification)
- **Pas de billet nominatif** - le billet doit être *identifiable*, pas *rattaché à une identité*
- **Pas de partenaire tiers** à intégrer

## 4. Acteurs

| Acteur | Rôle | Besoin principal |
|--|||
| Spectateur | Achète | Choisir séance + place, payer, recevoir son billet |
| Borne | Vend sur place | Même parcours, sans compte, paiement CB physique |
| Contrôleur | Filtre l'entrée | Scanner, verdict en < 1 s, même en réseau dégradé |
| Gérant | Exploite | Programmer, tarifer, suivre le remplissage, rembourser |

## 5. Exigences

### Fonctionnelles
- Consulter la programmation et les séances 
- Sélectionner ses places sur un plan de salle 
- Réserver temporairement les places pendant le paiement 
- Payer en ligne via le partenaire
- Recevoir un billet avec QR code signé 
- Contrôler un billet à l'entrée (authenticité + usage unique)
- Appliquer la bonne grille tarifaire
- Visualiser le taux de remplissage par séance 
- Annuler et rembourser un billet 
- Administrer films, séances, salles, tarifs 
- Définir un tarif exceptionnel sur un événement 

### Non fonctionnelles

| Exigence | Cible |
| -|-|
| **Charge** | ~1 800 places simultanées à l'ouverture des ventes ; pics week-end et événements |
| **Performance** | Affichage du plan de salle < 500 ms ; validation d'un scan < 200 ms |
| **Cohérence** | **Aucun double-booking**, jamais, même sous forte concurrence |
| **Disponibilité** | Le contrôle d'entrée doit fonctionner même si le réseau tombe |
| **Responsive** | Tous formats d'écran, du mobile à la borne tactile |
| **Sécurité** | Billet infalsifiable ; aucune donnée de carte stockée (délégation PSP) |
| **RGPD** | Données minimales, cohérent avec le billet non nominatif |

## 6. Architecture générale

### 6.1 Choix techniques et justification

| Composant | Choix | Pourquoi |
|--|-|-|
| Front public | SPA responsive (React/Vue) + rendu serveur des pages catalogue | Le catalogue doit être référencé et rapide ; le plan de salle doit être interactif |
| Front borne | Même application, mode kiosque plein écran | Un seul code à maintenir |
| App de scan | PWA avec cache local (Capacitor) | Fonctionne en réseau dégradé (NF4) |
| API | REST + JSON | Simple, cacheable, suffisant ici ; un WebSocket dédié pousse les mises à jour du plan de salle |
| Base | **PostgreSQL** | Gratuit, pratique et accessible |
| Cache / verrous | **Redis** | Réservations temporaires à expiration automatique, compteurs de remplissage |
| Asynchrone | File de messages | E-mails et remboursements ne doivent pas bloquer la réponse HTTP |
| Déploiement | Conteneurs, instances API sans état | Permet de scaler sur les pics du week-end |

Le **billet** est l'entité centrale : il porte son propre statut, ce qui rend le contrôle d'entrée indépendant du reste du système.

## 7. Mécanismes clés

### 7.1 Anti double-booking

C'est le risque numéro un : deux spectateurs qui cliquent sur le même siège à la même seconde.

Deux garde-fous complémentaires : le **verrou Redis à expiration** évite qu'un panier abandonné bloque un siège indéfiniment, et la **contrainte d'unicité en base** sur "(seance_id, siege_id)" garantit l'intégrité même si le cache tombe. Le cache accélère, la base arbitre.

### 7.2 Authenticité du billet

Le billet est **non nominatif mais infalsifiable**. Son QR code contient un identifiant et une **signature cryptographique** (HMAC-SHA256 avec une clé serveur, ou signature asymétrique si l'on veut que le scanner vérifie sans détenir le secret).

Falsifier un billet reviendrait à forger la signature sans la clé - hors de portée. Le contrôle se fait en deux temps :

1. Vérification de la signature - possible hors ligne.
2. **Vérification du statut** - le billet passe de "valide" à "utilisé" de façon atomique. Une deuxième présentation du même QR code est rejetée : c'est l'**anti-repasse**, qui bloque la photo du billet transmise à un ami.

En mode dégradé, le scanner accepte sur la seule signature et journalise localement ; la synchronisation ultérieure remonte les éventuels doublons.

### 7.3 Moteur de tarification

Le tarif n'est jamais écrit en dur. Une règle porte des critères (jour de la semaine, type de production, catégorie de client) et une priorité. Le moteur évalue les règles applicables et retient la plus prioritaire.

Le cas *« Terminator grandeur nature »* est traité comme un **événement à tarif unique**, priorité maximale, qui court-circuite toute la grille. Le tarif appliqué est **affiché au spectateur avant paiement** et **stocké sur le billet** - indispensable pour justifier le montant d'un remboursement.

### 7.4 Taux de remplissage

Un compteur par séance est maintenu dans Redis et incrémenté à l'émission de chaque billet. Le back-office l'affiche en temps réel (places vendues, disponibles, pourcentage).

### 7.5 Remboursement

Le billet passe en "remboursé", le siège est libéré et redevient vendable, et le remboursement est demandé au partenaire de paiement de façon asynchrone. Un billet déjà scanné ne peut plus être remboursé.

## 8. Points à valider avec le client

Quelques zones restent ouvertes et méritent d'être tranchées avant le développement :

- Délai limite de remboursement (jusqu'à la séance ? 24 h avant ?) et éventuels frais retenus
- Nombre maximum de places par commande"# projet_architecture_web" 
