import pulumi
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class Settings(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )

    namespace: str
    image: str
    replicas: int = Field(ge=1)
    ingress_host: str
    install_traefik: bool = True
    db_name: str
    db_user: str
    db_password: pulumi.Output[str]
    django_secret_key: pulumi.Output[str]

    @field_validator("namespace", "image", "db_name", "db_user")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("ingress_host")
    @classmethod
    def validate_ingress_host(cls, value: str) -> str:
        if not value:
            raise ValueError("must not be empty")
        if "://" in value:
            raise ValueError("must be a hostname, not a URL")
        if "/" in value:
            raise ValueError("must not contain a path")
        return value


def load_settings() -> Settings:
    config = pulumi.Config()
    raw_settings = {
        "namespace": config.require("namespace"),
        "image": config.require("image"),
        "replicas": config.get_int("replicas") or 1,
        "ingress_host": config.get("ingress_host") or "django.local",
        "install_traefik": config.get_bool("install_traefik"),
        "db_name": config.require("db_name"),
        "db_user": config.require("db_user"),
        "db_password": config.require_secret("db_password"),
        "django_secret_key": config.require_secret("django_secret_key"),
    }

    try:
        return Settings.model_validate(raw_settings)
    except ValidationError as exc:
        raise pulumi.RunError(
            f"Invalid Pulumi configuration for stack settings:\n{exc}"
        ) from exc
