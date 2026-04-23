from typing import Sequence

import pulumi
import pulumi_kubernetes as k8s

from common import (
    APP_CONFIG_NAME,
    APP_NAME,
    APP_SECRET_NAME,
    DJANGO_CONTAINER_PORT,
    DJANGO_SETTINGS_MODULE,
    POSTGRES_CLAIM_NAME,
    POSTGRES_IMAGE,
    POSTGRES_NAME,
    POSTGRES_PORT,
    POSTGRES_STORAGE_SIZE,
    POSTGRES_VOLUME_NAME,
    TRAEFIK_INGRESS_CLASS,
    labels,
    namespaced_metadata,
    secret_key_ref,
)
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
