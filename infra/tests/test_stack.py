import pulumi

import stack


def make_settings(**overrides):
    return stack.Settings.model_validate(
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


def test_namespaced_metadata_returns_expected_structure():
    assert stack.namespaced_metadata("django-stage", "app-config") == {
        "namespace": "django-stage",
        "name": "app-config",
    }


def test_labels_returns_expected_structure():
    assert stack.labels("django") == {"app": "django"}


def test_secret_key_ref_returns_expected_structure():
    assert stack.secret_key_ref("app-secret", "DATABASE_PASSWORD") == {
        "secretKeyRef": {
            "name": "app-secret",
            "key": "DATABASE_PASSWORD",
        }
    }


def test_main_creates_traefik_when_install_traefik_is_true(monkeypatch):
    calls = {"create_traefik": 0}

    monkeypatch.setattr(stack, "create_namespace", lambda settings: "django-dev")
    monkeypatch.setattr(stack, "create_app_configuration", lambda settings, ns: None)
    monkeypatch.setattr(stack, "create_postgres", lambda settings, ns: None)
    monkeypatch.setattr(stack, "create_django_app", lambda settings, ns: "django-svc")

    def fake_create_traefik():
        calls["create_traefik"] += 1
        return "traefik-release"

    monkeypatch.setattr(stack, "create_traefik", fake_create_traefik)
    monkeypatch.setattr(
        stack,
        "create_ingress",
        lambda namespace_name, ingress_host, dependencies: None,
    )
    monkeypatch.setattr(stack.pulumi, "export", lambda name, value: None)

    stack.main(settings=make_settings(install_traefik=True))

    assert calls["create_traefik"] == 1


def test_main_skips_traefik_when_install_traefik_is_false(monkeypatch):
    calls = {"create_traefik": 0, "dependencies": None}

    monkeypatch.setattr(stack, "create_namespace", lambda settings: "django-stage")
    monkeypatch.setattr(stack, "create_app_configuration", lambda settings, ns: None)
    monkeypatch.setattr(stack, "create_postgres", lambda settings, ns: None)
    monkeypatch.setattr(stack, "create_django_app", lambda settings, ns: "django-svc")

    def fake_create_traefik():
        calls["create_traefik"] += 1
        return "traefik-release"

    def fake_create_ingress(namespace_name, ingress_host, dependencies):
        calls["dependencies"] = dependencies

    monkeypatch.setattr(stack, "create_traefik", fake_create_traefik)
    monkeypatch.setattr(stack, "create_ingress", fake_create_ingress)
    monkeypatch.setattr(stack.pulumi, "export", lambda name, value: None)

    stack.main(settings=make_settings(install_traefik=False))

    assert calls["create_traefik"] == 0
    assert calls["dependencies"] == ["django-svc"]
