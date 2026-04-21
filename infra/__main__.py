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
        "DATABASE_NAME": db_name,
        "DATABASE_USER": db_user,
        "DJANGO_SETTINGS_MODULE": "mysite.settings",
        "IMAGE_PLACEHOLDER": image,
        "REPLICAS_PLACEHOLDER": str(replicas),
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

pulumi.export("namespace", namespace_name)
