from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://cinetint:cinetint@postgres:5432/cinetint"
    redis_url: str = "redis://redis:6379/0"
    qr_generator_url: str = "http://qr-generator:8001"

    # secret partagé entre services pour les routes /internal
    service_token: str = "dev-service-token"
    # clé des jetons du personnel (gérant, contrôleurs), partagée avec qr-verifier
    jwt_secret: str = "dev-jwt-secret-a-changer-en-production"
    jwt_duree_heures: int = 12

    cors_origins: str = "http://localhost:8080"

    gerant_mot_de_passe: str = "gerant"
    controleur_mot_de_passe: str = "controleur"

    donnees_demo: bool = True
    fuseau: str = "Europe/Paris"


settings = Settings()
