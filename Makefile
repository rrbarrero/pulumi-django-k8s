.PHONY: garage build run kind-create kind-delete kind-status

KIND_CLUSTER_NAME ?= pulumi-django-kind

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

%:
	@:
