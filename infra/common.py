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
