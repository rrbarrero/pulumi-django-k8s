# Pulumi Django on Kind

This repository is a small learning project that shows how to deploy a Django application to a local Kubernetes cluster created with Kind, using Pulumi as the infrastructure definition tool.

The stack includes:

- a Kind cluster for local Kubernetes
- a Pulumi state backend stored in an S3-compatible bucket served by local Garage
- a Django application packaged as a Docker image
- a PostgreSQL database running inside Kubernetes
- Traefik installed with a Helm chart from Pulumi
- two Pulumi stacks, `dev` and `stage`, deployed into the same cluster with different namespaces
- an Ingress that routes `django.local` and `django-stage.local` to different Django services
- a modular Pulumi codebase split into settings, shared resources, environment resources, and reusable components
- automated tests for Pulumi helpers, stack orchestration, and policy guardrails
- a GitHub Actions workflow that runs the Pulumi-related test suite on CI
- a small Django view that talks to the Kubernetes API and lists pods from its own namespace

## Project layout

- `infra/`: Pulumi program and tests
- `infra/settings.py`: typed and validated stack settings loaded from Pulumi config
- `infra/common.py`: shared constants and helper functions
- `infra/shared_resources.py`: shared cluster resources such as Traefik
- `infra/environment_resources.py`: namespaced environment resources
- `infra/components.py`: reusable Pulumi `ComponentResource` implementations for Postgres and Django
- `infra/policies.py`: Policy as Code guardrails enforced during stack execution
- `infra/tests/`: pytest suite for helpers, orchestration logic, and policies
- `pulumi-django/`: Django application and Docker image
- `kind-config.yaml`: Kind cluster configuration with port mappings for Traefik
- `Makefile`: helper commands for Kind and Docker image workflows
- `ops/pulumi-config.sh`: helper script to log Pulumi into the local S3-compatible backend

## Prerequisites

You will need the following tools installed locally:

- Docker
- Kind
- `kubectl`
- Pulumi
- Python 3.13
- `uv`

If you want to use the same Pulumi backend configured in this repository, you will also need the local Garage service started through Docker Compose.

## Pulumi backend

This project is configured to use a self-hosted Pulumi backend stored in an S3-compatible bucket exposed by Garage.

The helper script:

```bash
source ops/pulumi-config.sh
```

logs Pulumi into this backend:

```text
s3://pulumi-infra?endpoint=127.0.0.1:33900&disableSSL=true&s3ForcePathStyle=true
```

If you do not want to use the local Garage backend, you can log into any other Pulumi backend manually before running `pulumi up`.

## What the app does

The Django app is exposed through Traefik on:

- `http://django.local:30080/`
- `http://django-stage.local:30080/`

The root route and `/cluster-info/` return JSON with the pods visible from the app namespace.

The `dev` and `stage` stacks share the same Kind cluster and the same Traefik installation, but each stack has its own namespace, database, Django deployment, service, and ingress host. The `stage` stack is configured with `install_traefik: false`, so it reuses the Traefik release managed by `dev` and avoids stack conflicts around the shared Helm release.

The Pulumi program is intentionally structured as a small but realistic infrastructure codebase:

- settings are loaded from Pulumi config and validated with Pydantic
- environment resources are separated from shared resources
- PostgreSQL and Django are modeled as Pulumi `ComponentResource` classes
- policy checks are executed before creating selected resources

## Reproducing the setup

### 1. Start the local Pulumi backend

If you are using the local Garage-backed Pulumi state storage:

```bash
docker compose up -d
source ops/pulumi-config.sh
```

If you use a different Pulumi backend, log in with your usual `pulumi login` flow instead.

### 2. Create the Kind cluster

The repository includes a Kind config that maps:

- `30080` -> Traefik HTTP
- `30443` -> Traefik HTTPS

Create the cluster with:

```bash
make kind-create
```

### 3. Point the hostnames to your machine

Add these lines to `/etc/hosts`:

```text
127.0.0.1 django.local
127.0.0.1 django-stage.local
```

### 4. Build and load the Django image into Kind

```bash
make app-image-push
```

This builds the Docker image and loads it into the Kind cluster.

### 5. Deploy the infrastructure with Pulumi

Move into the Pulumi project and apply the stack:

```bash
cd infra
pulumi stack select dev
pulumi up --refresh
```

The default development stack configuration is stored in `infra/Pulumi.dev.yaml`.

To deploy the `stage` stack in the same cluster:

```bash
cd infra
pulumi stack select stage
pulumi up --refresh
```

The stage configuration is stored in `infra/Pulumi.stage.yaml`.

## Quality checks

The repository includes a small test suite for the infrastructure code:

```bash
make pulumi-test
```

This runs pytest against the Pulumi helpers, orchestration flow, and policies.

You can also run a higher-level check that executes a preview first and then the tests:

```bash
make pulumi-check
```

The CI workflow in `.github/workflows/pulumi-tests.yml` runs the Pulumi-related tests on push and pull request.

## Policy as Code

The project includes a lightweight Policy as Code layer in `infra/policies.py`. These policies act as guardrails during `pulumi preview` and `pulumi up`, and they are also covered by pytest.

Current policies include:

- container images must not use the `:latest` tag
- the `django-stage` environment must run at least `2` replicas
- only the `django-dev` environment may manage the shared Traefik release
- Kubernetes `Service` resources must not use `LoadBalancer`
- the application `Ingress` must use `ingressClassName: traefik`
- the `django-pod-reader` role must stay limited to `pods` with `get`, `list`, and `watch`

## Accessing the application

Once the deployment is ready, open:

```text
http://django.local:30080/
http://django-stage.local:30080/
```

You can also query the namespace pod view directly:

```text
http://django.local:30080/cluster-info/
http://django-stage.local:30080/cluster-info/
```

## Multi-environment example

The following output shows both environments running in the same cluster and each app only seeing pods from its own namespace:

```bash
$ curl http://django-stage.local:30080
{"config_source":"in-cluster","namespace":"django-stage","pods":[{"name":"django-c699fc6cd-h67xs","namespace":"django-stage","ip":"10.244.0.11"},{"name":"django-c699fc6cd-n7mdp","namespace":"django-stage","ip":"10.244.0.9"},{"name":"postgres-5d6986578-7z9gg","namespace":"django-stage","ip":"10.244.0.12"}]}

$ curl http://django.local:30080
{"config_source":"in-cluster","namespace":"django-dev","pods":[{"name":"django-c699fc6cd-5445p","namespace":"django-dev","ip":"10.244.0.5"},{"name":"postgres-788d6f6b44-5mp2f","namespace":"django-dev","ip":"10.244.0.8"}]}
```

You can also inspect both namespaces at once with:

```bash
$ kubectl get pods -A -o wide | grep -E '^(django-dev|django-stage)\s'

django-dev           django-c699fc6cd-5445p     1/1   Running   0              57m     10.244.0.5    pulumi-django-kind-control-plane   <none>   <none>
django-dev           postgres-788d6f6b44-5mp2f  1/1   Running   0              57m     10.244.0.8    pulumi-django-kind-control-plane   <none>   <none>
django-stage         django-c699fc6cd-h67xs     1/1   Running   2 (6m6s ago)   6m15s   10.244.0.11   pulumi-django-kind-control-plane   <none>   <none>
django-stage         django-c699fc6cd-n7mdp     1/1   Running   2 (6m6s ago)   6m15s   10.244.0.9    pulumi-django-kind-control-plane   <none>   <none>
django-stage         postgres-5d6986578-7z9gg   1/1   Running   0              6m15s   10.244.0.12   pulumi-django-kind-control-plane   <none>   <none>
```

## Updating the Django app

If you change application code, rebuild and reload the image, then restart the deployment:

```bash
make app-image-push
kubectl -n django-dev rollout restart deployment/django
kubectl -n django-dev rollout status deployment/django
```

Pulumi will not detect code-only changes if the image tag stays the same.

For `stage`, restart the deployment in the `django-stage` namespace:

```bash
kubectl -n django-stage rollout restart deployment/django
kubectl -n django-stage rollout status deployment/django
```

## Useful commands

Check the cluster:

```bash
make kind-status
make pulumi-test
make pulumi-check
kubectl get pods -A
kubectl get ingress -A
kubectl get svc -A
```

Recreate the cluster:

```bash
make kind-delete
make kind-create
make app-image-push
cd infra && pulumi stack select dev && pulumi up --refresh
cd infra && pulumi stack select stage && pulumi up --refresh
```

Inspect Django logs:

```bash
kubectl -n django-dev logs deployment/django --tail=100
```

Inspect Traefik logs:

```bash
kubectl -n traefik logs deployment/traefik --tail=100
```

## Notes

- The Django container runs `migrate` and `collectstatic` at startup.
- The Django app talks to the Kubernetes API using an in-cluster service account.
- The service account is restricted to listing pods only inside its own namespace.
- Traefik is installed from Helm through Pulumi, not by running Helm manually.
- The `dev` stack manages the shared Traefik release.
- The `stage` stack reuses that Traefik installation and only manages namespaced application resources plus its own ingress.
- The infrastructure code is split into modules to keep settings, shared resources, environment resources, and components separate.
- The Pulumi code is covered by pytest and checked in CI.
