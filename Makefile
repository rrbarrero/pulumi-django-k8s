.PHONY: garage build run

garage:
	docker exec -ti garage /garage $(filter-out $@,$(MAKECMDGOALS))

build:
	docker compose build

run:
	docker compose up -d && docker compose logs -f

%:
	@:
