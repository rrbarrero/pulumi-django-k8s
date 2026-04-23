import pulumi
import pulumi_kubernetes as k8s

from common import (
    APP_CONFIG_NAME,
    APP_NAME,
    APP_SECRET_NAME,
    DJANGO_CONTAINER_PORT,
    POSTGRES_CLAIM_NAME,
    POSTGRES_IMAGE,
    POSTGRES_NAME,
    POSTGRES_PORT,
    POSTGRES_STORAGE_SIZE,
    POSTGRES_VOLUME_NAME,
    labels,
    namespaced_metadata,
    secret_key_ref,
)
from policies import validate_role_policy, validate_service_policy
from settings import Settings


class PostgresComponent(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        settings: Settings,
        namespace_name: pulumi.Input[str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__("custom:infra:PostgresComponent", name, None, opts)

        postgres_labels = labels(POSTGRES_NAME)
        resource_opts = pulumi.ResourceOptions(parent=self)
        postgres_service_spec = {
            "selector": postgres_labels,
            "ports": [
                {
                    "port": POSTGRES_PORT,
                    "targetPort": POSTGRES_PORT,
                }
            ],
        }
        validate_service_policy(POSTGRES_NAME, postgres_service_spec)

        self.pvc = k8s.core.v1.PersistentVolumeClaim(
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
            opts=resource_opts,
        )

        self.deployment = k8s.apps.v1.Deployment(
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
                                    {
                                        "name": "POSTGRES_USER",
                                        "value": settings.db_user,
                                    },
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
            opts=resource_opts,
        )

        self.service = k8s.core.v1.Service(
            POSTGRES_NAME,
            metadata=namespaced_metadata(namespace_name, POSTGRES_NAME),
            spec=postgres_service_spec,
            opts=resource_opts,
        )

        self.register_outputs(
            {
                "pvc_name": self.pvc.metadata["name"],
                "service_name": self.service.metadata["name"],
            }
        )


class DjangoAppComponent(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        settings: Settings,
        namespace_name: pulumi.Input[str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__("custom:infra:DjangoAppComponent", name, None, opts)

        django_labels = labels(APP_NAME)
        resource_opts = pulumi.ResourceOptions(parent=self)
        role_rules = [
            {
                "apiGroups": [""],
                "resources": ["pods"],
                "verbs": ["get", "list", "watch"],
            }
        ]
        django_service_spec = {
            "selector": django_labels,
            "ports": [
                {
                    "port": DJANGO_CONTAINER_PORT,
                    "targetPort": DJANGO_CONTAINER_PORT,
                }
            ],
        }
        validate_role_policy("django-pod-reader", role_rules)
        validate_service_policy(APP_NAME, django_service_spec)

        self.service_account = k8s.core.v1.ServiceAccount(
            APP_NAME,
            metadata=namespaced_metadata(namespace_name, APP_NAME),
            opts=resource_opts,
        )

        self.role = k8s.rbac.v1.Role(
            "django-pod-reader",
            metadata=namespaced_metadata(namespace_name, "django-pod-reader"),
            rules=role_rules,
            opts=resource_opts,
        )

        self.role_binding = k8s.rbac.v1.RoleBinding(
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
            opts=resource_opts,
        )

        self.deployment = k8s.apps.v1.Deployment(
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
            opts=resource_opts,
        )

        self.service = k8s.core.v1.Service(
            APP_NAME,
            metadata=namespaced_metadata(namespace_name, APP_NAME),
            spec=django_service_spec,
            opts=resource_opts,
        )

        self.register_outputs(
            {
                "service_name": self.service.metadata["name"],
                "service_account_name": self.service_account.metadata["name"],
            }
        )
