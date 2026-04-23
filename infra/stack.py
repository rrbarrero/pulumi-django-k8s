import pulumi

from common import labels, namespaced_metadata, secret_key_ref
from environment_resources import (
    create_app_configuration,
    create_django_app,
    create_ingress,
    create_namespace,
    create_postgres,
)
from settings import Settings, load_settings
from shared_resources import create_traefik


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
