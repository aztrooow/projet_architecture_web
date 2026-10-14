# Réponses aux questions du cours (CSC 8567)

Le sujet de cette année est une billetterie de cinéma, réalisée en **FastAPI** (Python) et non en Django. Chaque question Django du cours est donc traitée avec l'équivalent exact de notre pile : FastAPI pour les routes et les pages, Jinja2 pour les gabarits, SQLAlchemy pour les modèles, Alembic pour les migrations. Les chemins cités sont ceux du dépôt.

Correspondance rapide entre Django et notre projet :

| Django | CinetINT |
|---|---|
| application `public` (pages HTML) | service **front** : `front/server/` (FastAPI + Jinja2) et `front/web/` (React) |
| application `api` (JSON) | service **back** : `back/app/routes/` (FastAPI) |
| `urls.py` | décorateurs `@app.get(...)` et `app.include_router(...)` |
| `views.py` | les fonctions de route (`accueil`, `infos`, `donnees_salles`...) |
| `templates/` | `front/server/templates/` |
| `models.py` | `back/app/models.py` (SQLAlchemy) |
| `settings.py`, `DJANGO_SETTINGS_MODULE` | variables d'environnement lues par `back/app/config.py` (pydantic-settings) |
| `manage.py makemigrations` / `migrate` | `alembic revision --autogenerate` / `alembic upgrade head` |
| `migrations/` | `back/migrations/versions/` |
| fixtures (`loaddata sample.json`) | `back/app/fixtures.py` (`python -m app.fixtures`) |
| `/admin` (interface Django) | `/admin` : espace gérant (React) et ses pages « Données » |

## Fonctionnement de Django (équivalent FastAPI)

### Quelle suite de requêtes et d'exécutions permet d'afficher une page HTML `index.html` à l'URL globale `/`, sans contexte de données ? Où sont les fichiers ?

Avec notre pile, pour une page sans donnée, on place trois choses dans le service front :

1. Le gabarit : `front/server/templates/index.html` (il peut étendre `base.html`, qui est dans le même dossier).
2. La route, dans `front/server/main.py`, qui est l'équivalent à la fois de `urls.py` et de `views.py` :

```py
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})
```

3. L'objet `templates = Jinja2Templates(directory=ICI / "templates")`, déjà déclaré dans ce fichier, qui dit où chercher les gabarits.

Il n'y a pas de fichier `urls.py` à « inclure » : la route est déclarée sur l'objet `app = FastAPI(...)`. Pour un projet plus gros, on découpe en `APIRouter` dans des modules séparés puis on les branche avec `app.include_router(...)`, comme le back le fait dans `back/app/main.py` (`for module in (catalogue, commandes, auth, admin, donnees, interne): app.include_router(module.router)`), ce qui correspond au `include('public.urls')` de Django.

La suite d'exécutions, pour notre vraie page d'accueil `/` (qui, elle, lit des données) :

1. Le navigateur envoie `GET /` à `http://localhost/`. Docker publie le port 80 de l'hôte vers le conteneur `proxy` (règle NAT).
2. nginx (`nginx/nginx.conf`) choisit le service selon le préfixe de l'URL : `/` ne correspond à aucun préfixe particulier, la requête part donc vers `front:8080` (le nom `front` est résolu par le DNS interne de Docker).
3. Le serveur `uvicorn` du conteneur `front` charge `server.main:app` (voir le `CMD` de `front/Dockerfile`) et FastAPI trouve la route `GET /`, la fonction `accueil` de `front/server/main.py`.
4. `accueil` appelle l'API du back (`lire_api("/api/programme")`, puis `/api/tarifs`) en HTTP vers `http://back:8000`, puis appelle `rendre(...)`.
5. `rendre` fait exécuter par Jinja2 le gabarit `front/server/templates/accueil.html` (qui étend `base.html` et importe `_macros.html`) avec le contexte (films, séances, grille) et y ajoute les fichiers JS et CSS produits par Vite (lus dans `web/dist/.vite/manifest.json`).
6. Le HTML rendu remonte par le proxy jusqu'au navigateur, qui télécharge ensuite `/assets/...` et `/static/...` (servis par le même front).

### Dans quelle(s) section(s) de quel(s) fichier(s) configure-t-on la base de données ?

L'adresse de la base est dans la variable d'environnement **`DATABASE_URL`**, lue par la classe `Settings` de `back/app/config.py` (champ `database_url`, pydantic-settings). Elle est ensuite utilisée à deux endroits :

- `back/app/db.py` : `create_async_engine(settings.database_url, ...)`, le moteur de l'application ;
- `back/migrations/env.py` : le moteur d'Alembic, quand on migre.

Sa valeur réelle est posée par `docker-compose.yml`, section `environment` du service `back` : `postgresql+asyncpg://cinetint:${POSTGRES_PASSWORD:-cinetint}@postgres:5432/cinetint` (le serveur s'appelle `postgres`, le nom du service de la base). Le conteneur PostgreSQL reçoit de son côté `POSTGRES_DB`, `POSTGRES_USER` et `POSTGRES_PASSWORD` dans la section `environment` du service `postgres`. Seul le back accède à la base : le front passe par l'API, les services QR n'en ont pas besoin.

### Dans quel(s) fichier(s) choisit-on le fichier de paramètres que le projet doit utiliser ?

Il n'y a pas de « fichier de paramètres » à choisir parmi plusieurs comme avec `DJANGO_SETTINGS_MODULE` : la configuration vient de l'**environnement du processus**, et le code est le même partout. Ce qui joue le rôle du choix de `settings.py` :

- `docker-compose.yml` : la section `environment` de chaque service fixe les variables de son conteneur. Le service `back-tests` (profil `tests`) utilise la même image mais une autre configuration (`DATABASE_URL` vers la base `cinetint_tests`, `DONNEES_DEMO: "false"`, `PROGRAMME_SOURCE: aucune`), comme on changerait de module de paramètres pour les tests ;
- `.env` (à la racine, copié depuis `.env.example`, ignoré par git) : Compose y lit les valeurs substituées dans `docker-compose.yml` (`${POSTGRES_PASSWORD:-cinetint}`, `${PROXY_PORT:-80}`...) ;
- `back/app/config.py` (`Settings`, avec `env_file=".env"` pour un lancement hors Docker), `front/server/main.py` (sa propre classe `Settings`), `qr-generator/app/main.py` et `qr-verifier/app/main.py` : chaque service déclare ses variables avec une valeur par défaut de développement.

Les deux « points d'entrée » qui lisent cette configuration sont, comme `wsgi.py` et `manage.py` en Django : `app/main.py`, chargé par `uvicorn app.main:app` pour servir les requêtes (équivalent de `wsgi.py`), et `alembic.ini` avec `migrations/env.py`, chargés par la commande `alembic` pour migrer (équivalent de `manage.py`). Les deux importent `app.config.settings`, donc lisent exactement la même `DATABASE_URL`.

### Quel est l'effet de `alembic revision --autogenerate` et de `alembic upgrade head` ? Quels fichiers sont mis en oeuvre ?

(Équivalents de `python manage.py makemigrations` et `python manage.py migrate`, lancés depuis `back/`.)

- **`alembic revision --autogenerate -m "message"`** compare les tables décrites par les modèles (`Base.metadata`, dans `back/app/models.py`) à l'état réel de la base de données (il se connecte donc à la base) et **écrit** un fichier de migration `back/migrations/versions/<numéro>_<message>.py` contenant `upgrade()` (les opérations pour passer à la nouvelle version) et `downgrade()` (pour revenir en arrière). Rien n'est modifié dans la base. Le fichier se relit avant de le garder : c'est ainsi qu'a été produite `0001_schema_initial.py`, qui crée les douze tables.
- **`alembic upgrade head`** **applique** les migrations non encore jouées, dans l'ordre de leur chaîne (`revision` et `down_revision`), jusqu'à la dernière (`head`). Pour chacune, Alembic traduit `upgrade()` en SQL (`CREATE TABLE`, `CREATE INDEX`...), l'exécute dans une transaction, puis note la version atteinte dans la table **`alembic_version`** de la base. Relancée sur une base à jour, la commande ne fait rien. Chez nous elle est lancée à chaque démarrage du conteneur `back` par `back/entrypoint.sh`, sous un verrou consultatif PostgreSQL pour que plusieurs répliques ne migrent pas en même temps.

Fichiers mis en oeuvre :

| Fichier | Rôle |
|---|---|
| `back/app/models.py` | modèles SQLAlchemy : la description voulue du schéma |
| `back/app/config.py` | fournit `DATABASE_URL` |
| `back/alembic.ini` | configuration d'Alembic (dossier des migrations, journalisation) |
| `back/migrations/env.py` | connexion à la base, verrou, lancement des migrations (équivalent du moteur de `manage.py`) |
| `back/migrations/script.py.mako` | gabarit des fichiers de migration générés |
| `back/migrations/versions/*.py` | les migrations (équivalent du dossier `migrations/` d'une application Django) |
| table `alembic_version` (en base) | la version actuelle de la base |

Les données initiales (salles, sièges, catégories, tarifs, comptes) ne sont pas dans les migrations : elles sont chargées juste après par `python -m app.fixtures`, comme `loaddata` après `migrate`, de façon idempotente.

## Fonctionnement de Docker

### Effet et syntaxe de `FROM`, `RUN`, `WORKDIR`, `EXPOSE`, `CMD`

Exemples tirés de `back/Dockerfile` :

- `FROM python:3.13-slim AS base` : image de départ, téléchargée depuis Docker Hub. `AS base` nomme l'étape (construction en plusieurs étapes : `base`, puis `tests`, puis l'image finale). `front/Dockerfile` en utilise aussi une pour compiler l'application React (`FROM node:24-alpine AS web`).
- `RUN pip install -r requirements.txt` : exécute une commande shell **pendant la construction** de l'image ; le résultat (ici les paquets Python) est enregistré dans une nouvelle couche de l'image.
- `WORKDIR /app` : définit le répertoire courant des instructions suivantes (`COPY`, `RUN`, `CMD`) et du processus du conteneur ; il le crée s'il n'existe pas.
- `EXPOSE 8000` : **documente** le port sur lequel le service écoute. Cela ne publie rien sur l'hôte : la publication se fait avec `ports` dans le compose (ou `-p` avec `docker run`).
- `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]` : commande lancée **au démarrage du conteneur** (pas à la construction), sous forme de tableau (sans shell). Dans notre back, `ENTRYPOINT ["/app/entrypoint.sh"]` s'y ajoute : le script lance les migrations et les fixtures puis fait `exec "$@"`, c'est-à-dire exécute le `CMD`.

### Dans le `docker-compose.yml`, effet des mentions `ports`, `build`, `depends_on`, `environment`

- **`ports`** : `- "127.0.0.1:${PROXY_PORT:-80}:80"` (service `proxy`) publie le port 80 du conteneur sur le port `PROXY_PORT` de l'hôte (80 par défaut), **uniquement sur l'interface 127.0.0.1**. Docker installe pour cela une règle NAT (DNAT) qui redirige l'hôte vers l'adresse du conteneur sur le réseau `front`. Le proxy est le seul service qui publie un port.
- **`build`** : `build: ./back` indique le dossier (le contexte) et, par défaut, le `Dockerfile` qu'il contient, pour construire l'image du service. La forme longue précise aussi l'étape visée : `build: { context: ./back, target: tests }` pour `back-tests`.
- **`depends_on`** : ordonne le démarrage. Sous la forme courte (`depends_on: [back]`), Compose garantit seulement que `back` est **démarré** avant, pas qu'il est prêt. Avec `condition: service_healthy` (utilisé pour `postgres` et `redis` côté back, et pour les quatre services côté proxy), Compose attend que le `healthcheck` du service passe au vert. C'est ce qui évite que le back démarre avant que la base accepte les connexions.
- **`environment`** : définit les variables d'environnement du conteneur, par exemple `DATABASE_URL`, `REDIS_URL` pour le back. Les valeurs peuvent contenir `${VARIABLE}` ou `${VARIABLE:-défaut}` : Compose les remplace par la valeur du shell ou du fichier `.env` de la racine, ou par la valeur par défaut. `<<: *secrets` réutilise un bloc commun (ancre YAML) pour `SERVICE_TOKEN`, `JWT_SECRET`, `CORS_ORIGINS`.

### Une méthode pour définir des variables d'environnement dans un conteneur

Plusieurs, dont celles utilisées dans ce dépôt :

- la section `environment:` du `docker-compose.yml` (méthode du projet) ;
- le fichier `.env` de la racine, qui alimente les `${...}` du compose ;
- l'instruction `ENV` d'un Dockerfile (par exemple `ENV PYTHONUNBUFFERED=1` dans `back/Dockerfile`) ;
- `env_file: .env` dans le compose, pour injecter un fichier entier (non utilisé ici) ;
- `docker run -e NOM=valeur` ou `docker run --env-file fichier` quand on n'utilise pas Compose.

### Dans un même réseau Docker, comment adresser le serveur d'un conteneur `web` depuis un conteneur `nginx`, sans utiliser les adresses IP ?

Docker embarque un **serveur DNS** (à l'adresse 127.0.0.11 dans chaque conteneur) pour les réseaux définis par l'utilisateur. Il résout le **nom du service** (et ses alias) en l'adresse IP du conteneur sur ce réseau. Depuis `nginx`, on adresse donc le serveur du conteneur `web` par `web:8000`, par exemple `proxy_pass http://web:8000;`.

Dans notre projet, `nginx/nginx.conf` fait exactement cela : `set $service_back http://back:8000; proxy_pass $service_back;`, avec `resolver 127.0.0.11 valid=5s;` pour que nginx demande le nom au DNS de Docker à chaque requête (il suit ainsi un conteneur recréé, dont l'adresse change). Le DNS ne répond que pour les conteneurs du même réseau : le proxy est sur le réseau `front`, il résout `front`, `back`, `qr-generator` et `qr-verifier`, mais pas `postgres`, qui n'est que sur le réseau `back`. Le réseau par défaut `docker0` n'a pas cette résolution par nom, d'où le choix de réseaux nommés (`front` et `back`) dans le compose.

## Sources

- Alembic, environnement asynchrone et commandes : <https://alembic.sqlalchemy.org/en/latest/cookbook.html>, <https://alembic.sqlalchemy.org/en/latest/api/runtime.html>
- nginx, `proxy_pass` avec variables, `proxy_buffering` : <https://nginx.org/en/docs/http/ngx_http_proxy_module.html>
- Docker Compose, services (`ports`, `depends_on`, `environment`) : <https://docs.docker.com/reference/compose-file/services/>
- Docker, réseau « bridge » défini par l'utilisateur et résolution par nom : <https://docs.docker.com/engine/network/drivers/bridge/>
