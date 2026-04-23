from typing import Sequence

import pulumi
import pulumi_kubernetes as k8s

from common import (
    APP_NAME,
    APP_CONFIG_NAME,
    APP_SECRET_NAME,
    DJANGO_CONTAINER_PORT,
    DJANGO_SETTINGS_MODULE,
    POSTGRES_NAME,
    POSTGRES_PORT,
    TRAEFIK_INGRESS_CLASS,
    namespaced_metadata,
)
from components import DjangoAppComponent, PostgresComponent
from policies import validate_ingress_policy
from settings import Settings


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
    PostgresComponent("postgres", settings, namespace_name)


def create_django_app(
    settings: Settings,
    namespace_name: pulumi.Input[str],
) -> k8s.core.v1.Service:
    django_app = DjangoAppComponent("django", settings, namespace_name)
    return django_app.service


def create_ingress(
    namespace_name: pulumi.Input[str],
    ingress_host: str,
    dependencies: Sequence[pulumi.Resource],
) -> None:
    ingress_spec = {
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
    }
    validate_ingress_policy(APP_NAME, ingress_spec)

    k8s.networking.v1.Ingress(
        APP_NAME,
        metadata={
            **namespaced_metadata(namespace_name, APP_NAME),
            "annotations": {
                "pulumi.com/skipAwait": "true",
            },
        },
        spec=ingress_spec,
        opts=pulumi.ResourceOptions(depends_on=dependencies),
    )
