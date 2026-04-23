from common import TRAEFIK_INGRESS_CLASS
from settings import Settings


class PolicyViolation(ValueError):
    pass


def _raise(message: str) -> None:
    raise PolicyViolation(message)


def validate_settings_policies(settings: Settings) -> None:
    if settings.image.endswith(":latest"):
        _raise("Container images must use an explicit tag instead of ':latest'.")

    if settings.namespace == "django-stage" and settings.replicas < 2:
        _raise("The 'django-stage' environment must run at least 2 replicas.")

    if settings.install_traefik and settings.namespace != "django-dev":
        _raise("Only the 'django-dev' environment may manage the shared Traefik release.")


def validate_service_policy(service_name: str, spec: dict) -> None:
    service_type = spec.get("type")
    if service_type == "LoadBalancer":
        _raise(f"Service '{service_name}' must not use type LoadBalancer.")


def validate_ingress_policy(ingress_name: str, spec: dict) -> None:
    ingress_class_name = spec.get("ingressClassName")
    if ingress_class_name != TRAEFIK_INGRESS_CLASS:
        _raise(
            f"Ingress '{ingress_name}' must use ingressClassName='{TRAEFIK_INGRESS_CLASS}'."
        )


def validate_role_policy(role_name: str, rules: list[dict]) -> None:
    if role_name != "django-pod-reader":
        return

    expected_resources = {"pods"}
    allowed_verbs = {"get", "list", "watch"}

    for rule in rules:
        resources = set(rule.get("resources", []))
        verbs = set(rule.get("verbs", []))
        if resources != expected_resources:
            _raise(
                "Role 'django-pod-reader' must grant access only to the 'pods' resource."
            )
        if not verbs.issubset(allowed_verbs):
            _raise(
                "Role 'django-pod-reader' may only grant get, list and watch verbs."
            )
