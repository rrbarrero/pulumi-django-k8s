.PHONY: garage build run kind-create kind-delete kind-status app-image-build app-image-load app-image-push

KIND_CLUSTER_NAME ?= pulumi-django-kind
APP_IMAGE_NAME ?= pulumi-django
APP_IMAGE_TAG ?= dev
APP_IMAGE ?= $(APP_IMAGE_NAME):$(APP_IMAGE_TAG)

garage:
	docker exec -ti garage /garage $(filter-out $@,$(MAKECMDGOALS))

build:
	docker compose build

run:
	docker compose up -d && docker compose logs -f

kind-create:
	kind create cluster --name $(KIND_CLUSTER_NAME)

kind-delete:
	kind delete cluster --name $(KIND_CLUSTER_NAME)

kind-status:
	kind get clusters

app-image-build:
	docker build -t $(APP_IMAGE) pulumi-django

app-image-load:
	kind load docker-image $(APP_IMAGE) --name $(KIND_CLUSTER_NAME)

app-image-push: app-image-build app-image-load

%:
	@:
