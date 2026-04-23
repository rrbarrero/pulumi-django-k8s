from typing import Sequence

import pulumi
import pulumi_kubernetes as k8s
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


APP_NAME = "django"
APP_SECRET_NAME = "app-secret"
APP_CONFIG_NAME = "app-config"
POSTGRES_NAME = "postgres"
POSTGRES_IMAGE = "postgres:16"
POSTGRES_PORT = 5432
POSTGRES_VOLUME_NAME = "postgres-data"
POSTGRES_CLAIM_NAME = "postgres-pvc"
POSTGRES_STORAGE_SIZE = "200Mi"
DJANGO_CONTAINER_PORT = 8000
TRAEFIK_NAME = "traefik"
TRAEFIK_NAMESPACE = "traefik"
TRAEFIK_HTTP_NODE_PORT = 30080
TRAEFIK_HTTPS_NODE_PORT = 30443
TRAEFIK_INGRESS_CLASS = "traefik"
DJANGO_SETTINGS_MODULE = "pulumik8s.settings"


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


def namespaced_metadata(namespace_name, name):
    return {
        "namespace": namespace_name,
        "name": name,
    }


def labels(app_name):
    return {"app": app_name}


def secret_key_ref(name, key):
    return {
        "secretKeyRef": {
            "name": name,
            "key": key,
        }
    }


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


def create_namespace(settings: Settings) -> pulumi.Output[str]:
    namespace = k8s.core.v1.Namespace(
        "ns",
        metadata={"name": settings.namespace},
    )
    return namespace.metadata["name"]


def create_app_configuration(
    settings: Settings,
    namespace_name: pulumi.Input[str],
) -> None:
    k8s.core.v1.Secret(
        APP_SECRET_NAME,
        metadata=namespaced_metadata(namespace_name, APP_SECRET_NAME),
        string_data={
            "DATABASE_PASSWORD": settings.db_password,
            "DJANGO_SECRET_KEY": settings.django_secret_key,
        },
    )

    k8s.core.v1.ConfigMap(
        APP_CONFIG_NAME,
        metadata=namespaced_metadata(namespace_name, APP_CONFIG_NAME),
        data={
            "DATABASE_HOST": POSTGRES_NAME,
            "DATABASE_PORT": str(POSTGRES_PORT),
            "DATABASE_NAME": settings.db_name,
            "DATABASE_USER": settings.db_user,
            "DJANGO_ALLOWED_HOSTS": ",".join(
                [settings.ingress_host, "localhost", "127.0.0.1", "[::1]"]
            ),
            "DJANGO_SETTINGS_MODULE": DJANGO_SETTINGS_MODULE,
        },
    )


def create_postgres(
    settings: Settings,
    namespace_name: pulumi.Input[str],
) -> None:
    postgres_labels = labels(POSTGRES_NAME)

    k8s.core.v1.PersistentVolumeClaim(
        POSTGRES_CLAIM_NAME,
        metadata=namespaced_metadata(namespace_name, POSTGRES_CLAIM_NAME),
        spec={
            "accessModes": ["ReadWriteOnce"],
            "resources": {
                "requests": {
                    "storage": POSTGRES_STORAGE_SIZE,
                },
            },
        },
    )

    k8s.apps.v1.Deployment(
        POSTGRES_NAME,
        metadata=namespaced_metadata(namespace_name, POSTGRES_NAME),
        spec={
            "selector": {
                "matchLabels": postgres_labels,
            },
            "replicas": 1,
            "template": {
                "metadata": {
                    "labels": postgres_labels,
                },
                "spec": {
                    "containers": [
                        {
                            "name": POSTGRES_NAME,
                            "image": POSTGRES_IMAGE,
                            "ports": [{"containerPort": POSTGRES_PORT}],
                            "env": [
                                {"name": "POSTGRES_DB", "value": settings.db_name},
                                {"name": "POSTGRES_USER", "value": settings.db_user},
                                {
                                    "name": "POSTGRES_PASSWORD",
                                    "valueFrom": secret_key_ref(
                                        APP_SECRET_NAME,
                                        "DATABASE_PASSWORD",
                                    ),
                                },
                            ],
                            "volumeMounts": [
                                {
                                    "name": POSTGRES_VOLUME_NAME,
                                    "mountPath": "/var/lib/postgresql/data",
                                }
                            ],
                        }
                    ],
                    "volumes": [
                        {
                            "name": POSTGRES_VOLUME_NAME,
                            "persistentVolumeClaim": {
                                "claimName": POSTGRES_CLAIM_NAME,
                            },
                        }
                    ],
                },
            },
        },
    )

    k8s.core.v1.Service(
        POSTGRES_NAME,
        metadata=namespaced_metadata(namespace_name, POSTGRES_NAME),
        spec={
            "selector": postgres_labels,
            "ports": [
                {
                    "port": POSTGRES_PORT,
                    "targetPort": POSTGRES_PORT,
                }
            ],
        },
    )


def create_django_app(
    settings: Settings,
    namespace_name: pulumi.Input[str],
) -> k8s.core.v1.Service:
    django_labels = labels(APP_NAME)

    k8s.core.v1.ServiceAccount(
        APP_NAME,
        metadata=namespaced_metadata(namespace_name, APP_NAME),
    )

    k8s.rbac.v1.Role(
        "django-pod-reader",
        metadata=namespaced_metadata(namespace_name, "django-pod-reader"),
        rules=[
            {
                "apiGroups": [""],
                "resources": ["pods"],
                "verbs": ["get", "list", "watch"],
            }
        ],
    )

    k8s.rbac.v1.RoleBinding(
        "django-pod-reader",
        metadata=namespaced_metadata(namespace_name, "django-pod-reader"),
        role_ref={
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": "django-pod-reader",
        },
        subjects=[
            {
                "kind": "ServiceAccount",
                "name": APP_NAME,
                "namespace": namespace_name,
            }
        ],
    )

    k8s.apps.v1.Deployment(
        APP_NAME,
        metadata=namespaced_metadata(namespace_name, APP_NAME),
        spec={
            "selector": {
                "matchLabels": django_labels,
            },
            "replicas": settings.replicas,
            "template": {
                "metadata": {
                    "labels": django_labels,
                },
                "spec": {
                    "serviceAccountName": APP_NAME,
                    "containers": [
                        {
                            "name": APP_NAME,
                            "image": settings.image,
                            "imagePullPolicy": "IfNotPresent",
                            "ports": [{"containerPort": DJANGO_CONTAINER_PORT}],
                            "envFrom": [
                                {
                                    "configMapRef": {
                                        "name": APP_CONFIG_NAME,
                                    }
                                }
                            ],
                            "env": [
                                {
                                    "name": "DATABASE_PASSWORD",
                                    "valueFrom": secret_key_ref(
                                        APP_SECRET_NAME,
                                        "DATABASE_PASSWORD",
                                    ),
                                },
                                {
                                    "name": "DJANGO_SECRET_KEY",
                                    "valueFrom": secret_key_ref(
                                        APP_SECRET_NAME,
                                        "DJANGO_SECRET_KEY",
                                    ),
                                },
                                {
                                    "name": "K8S_NAMESPACE",
                                    "valueFrom": {
                                        "fieldRef": {
                                            "fieldPath": "metadata.namespace",
                                        }
                                    },
                                },
                            ],
                        }
                    ],
                },
            },
        },
    )

    return k8s.core.v1.Service(
        APP_NAME,
        metadata=namespaced_metadata(namespace_name, APP_NAME),
        spec={
            "selector": django_labels,
            "ports": [
                {
                    "port": DJANGO_CONTAINER_PORT,
                    "targetPort": DJANGO_CONTAINER_PORT,
                }
            ],
        },
    )


def create_traefik() -> k8s.helm.v3.Release:
    return k8s.helm.v3.Release(
        TRAEFIK_NAME,
        name=TRAEFIK_NAME,
        chart=TRAEFIK_NAME,
        repository_opts={
            "repo": "https://traefik.github.io/charts",
        },
        namespace=TRAEFIK_NAMESPACE,
        create_namespace=True,
        values={
            "service": {
                "type": "NodePort",
            },
            "ingressClass": {
                "enabled": True,
                "isDefaultClass": False,
                "name": TRAEFIK_INGRESS_CLASS,
            },
            "ports": {
                "web": {
                    "nodePort": TRAEFIK_HTTP_NODE_PORT,
                },
                "websecure": {
                    "nodePort": TRAEFIK_HTTPS_NODE_PORT,
                },
            },
            "providers": {
                "kubernetesIngress": {
                    "ingressClass": TRAEFIK_INGRESS_CLASS,
                },
                "kubernetesCRD": {
                    "ingressClass": TRAEFIK_INGRESS_CLASS,
                },
            },
        },
    )


def create_ingress(
    namespace_name: pulumi.Input[str],
    ingress_host: str,
    dependencies: Sequence[pulumi.Resource],
) -> None:
    k8s.networking.v1.Ingress(
        APP_NAME,
        metadata={
            **namespaced_metadata(namespace_name, APP_NAME),
            "annotations": {
                "pulumi.com/skipAwait": "true",
            },
        },
        spec={
            "ingressClassName": TRAEFIK_INGRESS_CLASS,
            "rules": [
                {
                    "host": ingress_host,
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": APP_NAME,
                                        "port": {
                                            "number": DJANGO_CONTAINER_PORT,
                                        },
                                    }
                                },
                            }
                        ]
                    },
                }
            ],
        },
        opts=pulumi.ResourceOptions(depends_on=dependencies),
    )


def main(settings: Settings | None = None) -> None:
    resolved_settings = settings or load_settings()
    namespace_name = create_namespace(resolved_settings)
    create_app_configuration(resolved_settings, namespace_name)
    create_postgres(resolved_settings, namespace_name)
    django_service = create_django_app(resolved_settings, namespace_name)

    ingress_dependencies = [django_service]
    if resolved_settings.install_traefik:
        ingress_dependencies.append(create_traefik())

    create_ingress(
        namespace_name,
        resolved_settings.ingress_host,
        ingress_dependencies,
    )

    pulumi.export("namespace", namespace_name)
    pulumi.export("ingress_host", resolved_settings.ingress_host)
    pulumi.export(
        "ingress_url",
        pulumi.Output.concat("http://", resolved_settings.ingress_host),
    )
