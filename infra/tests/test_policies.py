import pulumi
import pytest

from policies import (
    PolicyViolation,
    validate_ingress_policy,
    validate_role_policy,
    validate_service_policy,
    validate_settings_policies,
)
from settings import Settings


def make_settings(**overrides):
    return Settings.model_validate(
        {
            "namespace": "django-dev",
            "image": "pulumi-django:dev",
            "replicas": 1,
            "ingress_host": "django.local",
            "install_traefik": True,
            "db_name": "appdb",
            "db_user": "appuser",
            "db_password": pulumi.Output.secret("db-password"),
            "django_secret_key": pulumi.Output.secret("django-secret"),
            **overrides,
        }
    )


def test_settings_policy_rejects_latest_image_tag():
    with pytest.raises(PolicyViolation, match="explicit tag"):
        validate_settings_policies(make_settings(image="pulumi-django:latest"))


def test_settings_policy_requires_two_replicas_for_stage():
    with pytest.raises(PolicyViolation, match="at least 2 replicas"):
        validate_settings_policies(
            make_settings(
                namespace="django-stage",
                replicas=1,
                ingress_host="django-stage.local",
                install_traefik=False,
            )
        )


def test_settings_policy_prevents_non_dev_stacks_from_managing_traefik():
    with pytest.raises(PolicyViolation, match="manage the shared Traefik"):
        validate_settings_policies(
            make_settings(
                namespace="django-stage",
                replicas=2,
                ingress_host="django-stage.local",
                install_traefik=True,
            )
        )


def test_service_policy_rejects_load_balancers():
    with pytest.raises(PolicyViolation, match="LoadBalancer"):
        validate_service_policy("django", {"type": "LoadBalancer"})


def test_ingress_policy_requires_traefik_class():
    with pytest.raises(PolicyViolation, match="ingressClassName='traefik'"):
        validate_ingress_policy("django", {"ingressClassName": "nginx"})


def test_role_policy_rejects_excessive_permissions():
    with pytest.raises(PolicyViolation, match="only grant get, list and watch"):
        validate_role_policy(
            "django-pod-reader",
            [
                {
                    "apiGroups": [""],
                    "resources": ["pods"],
                    "verbs": ["get", "list", "watch", "delete"],
                }
            ],
        )


def test_valid_project_policies_pass():
    validate_settings_policies(make_settings())
    validate_service_policy("django", {"selector": {"app": "django"}})
    validate_ingress_policy("django", {"ingressClassName": "traefik"})
    validate_role_policy(
        "django-pod-reader",
        [
            {
                "apiGroups": [""],
                "resources": ["pods"],
                "verbs": ["get", "list", "watch"],
            }
        ],
    )
