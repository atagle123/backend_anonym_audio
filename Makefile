IMAGE_NAME ?= audio-flag-service
CONTAINER_NAME ?= audio-flag-service
DOCKER ?= docker

.PHONY: docker-build docker-run docker-logs

docker-build:
	$(DOCKER) build -t $(IMAGE_NAME) .

docker-run:
	$(DOCKER) run --rm -d \
		--name $(CONTAINER_NAME) \
		--env-file .env \
		-p 8000:8000 \
		$(IMAGE_NAME)

docker-logs:
	$(DOCKER) logs -f $(CONTAINER_NAME)
