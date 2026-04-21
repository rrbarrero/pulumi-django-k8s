import pulumi
import pulumi_kubernetes as k8s


def namespaced_metadata(namespace_name, name):
    return {
        "namespace": namespace_name,
        "name": name,
    }


def secret_key_ref(name, key):
    return {
        "secretKeyRef": {
            "name": name,
            "key": key,
        }
    }


config = pulumi.Config()

namespace = config.require("namespace")
image = config.require("image")
replicas = config.get_int("replicas") or 1
ingress_host = config.get("ingress_host") or "django.local"
db_name = config.require("db_name")
db_user = config.require("db_user")
db_password = config.require_secret("db_password")
django_secret_key = config.require_secret("django_secret_key")

ns = k8s.core.v1.Namespace(
    "ns",
    metadata={"name": namespace},
)

namespace_name = ns.metadata["name"]

app_secret = k8s.core.v1.Secret(
    "app-secret",
    metadata=namespaced_metadata(namespace_name, "app-secret"),
    string_data={
        "DATABASE_PASSWORD": db_password,
        "DJANGO_SECRET_KEY": django_secret_key,
    },
)

app_config = k8s.core.v1.ConfigMap(
    "app-config",
    metadata=namespaced_metadata(namespace_name, "app-config"),
    data={
        "DATABASE_HOST": "postgres",
        "DATABASE_PORT": "5432",
        "DATABASE_NAME": db_name,
        "DATABASE_USER": db_user,
        "DJANGO_ALLOWED_HOSTS": ",".join(
            [ingress_host, "localhost", "127.0.0.1", "[::1]"]
        ),
        "DJANGO_SETTINGS_MODULE": "pulumik8s.settings",
    },
)

postgres_pvc = k8s.core.v1.PersistentVolumeClaim(
    "postgres-pvc",
    metadata=namespaced_metadata(namespace_name, "postgres-pvc"),
    spec={
        "accessModes": ["ReadWriteOnce"],
        "resources": {
            "requests": {
                "storage": "200Mi",
            },
        },
    },
)

postgres_labels = {"app": "postgres"}
postgres_volume_name = "postgres-data"
postgres_claim_name = "postgres-pvc"
postgres_secret_name = "app-secret"

postgres_deployment = k8s.apps.v1.Deployment(
    "postgres",
    metadata=namespaced_metadata(namespace_name, "postgres"),
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
                        "name": "postgres",
                        "image": "postgres:16",
                        "ports": [{"containerPort": 5432}],
                        "env": [
                            {"name": "POSTGRES_DB", "value": db_name},
                            {"name": "POSTGRES_USER", "value": db_user},
                            {
                                "name": "POSTGRES_PASSWORD",
                                "valueFrom": secret_key_ref(
                                    postgres_secret_name,
                                    "DATABASE_PASSWORD",
                                ),
                            },
                        ],
                        "volumeMounts": [
                            {
                                "name": postgres_volume_name,
                                "mountPath": "/var/lib/postgresql/data",
                            }
                        ],
                    }
                ],
                "volumes": [
                    {
                        "name": postgres_volume_name,
                        "persistentVolumeClaim": {
                            "claimName": postgres_claim_name,
                        },
                    }
                ],
            },
        },
    },
)

postgres_service = k8s.core.v1.Service(
    "postgres",
    metadata=namespaced_metadata(namespace_name, "postgres"),
    spec={
        "selector": postgres_labels,
        "ports": [
            {
                "port": 5432,
                "targetPort": 5432,
            }
        ],
    },
)

django_labels = {"app": "django"}

django_deployment = k8s.apps.v1.Deployment(
    "django",
    metadata=namespaced_metadata(namespace_name, "django"),
    spec={
        "selector": {
            "matchLabels": django_labels,
        },
        "replicas": replicas,
        "template": {
            "metadata": {
                "labels": django_labels,
            },
            "spec": {
                "containers": [
                    {
                        "name": "django",
                        "image": image,
                        "imagePullPolicy": "IfNotPresent",
                        "ports": [{"containerPort": 8000}],
                        "envFrom": [
                            {
                                "configMapRef": {
                                    "name": "app-config",
                                }
                            }
                        ],
                        "env": [
                            {
                                "name": "DATABASE_PASSWORD",
                                "valueFrom": secret_key_ref(
                                    "app-secret",
                                    "DATABASE_PASSWORD",
                                ),
                            },
                            {
                                "name": "DJANGO_SECRET_KEY",
                                "valueFrom": secret_key_ref(
                                    "app-secret",
                                    "DJANGO_SECRET_KEY",
                                ),
                            },
                        ],
                    }
                ],
            },
        },
    },
)

django_service = k8s.core.v1.Service(
    "django",
    metadata=namespaced_metadata(namespace_name, "django"),
    spec={
        "selector": django_labels,
        "ports": [
            {
                "port": 8000,
                "targetPort": 8000,
            }
        ],
    },
)

traefik = k8s.helm.v3.Release(
    "traefik",
    name="traefik",
    chart="traefik",
    repository_opts={
        "repo": "https://traefik.github.io/charts",
    },
    namespace="traefik",
    create_namespace=True,
    values={
        "service": {
            "type": "NodePort",
        },
        "ingressClass": {
            "enabled": True,
            "isDefaultClass": False,
            "name": "traefik",
        },
        "ports": {
            "web": {
                "nodePort": 30080,
            },
            "websecure": {
                "nodePort": 30443,
            },
        },
        "providers": {
            "kubernetesIngress": {
                "ingressClass": "traefik",
            },
            "kubernetesCRD": {
                "ingressClass": "traefik",
            },
        },
    },
)

django_ingress = k8s.networking.v1.Ingress(
    "django",
    metadata={
        **namespaced_metadata(namespace_name, "django"),
        "annotations": {
            "pulumi.com/skipAwait": "true",
        },
    },
    spec={
        "ingressClassName": "traefik",
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
                                    "name": "django",
                                    "port": {
                                        "number": 8000,
                                    },
                                }
                            },
                        }
                    ]
                },
            }
        ],
    },
    opts=pulumi.ResourceOptions(depends_on=[traefik, django_service]),
)

pulumi.export("namespace", namespace_name)
pulumi.export("ingress_host", ingress_host)
pulumi.export("ingress_url", pulumi.Output.concat("http://", ingress_host))
