# -----------------------------
# Configuration
# -----------------------------
SHELL := /bin/bash
-include .env
export PROJECT_ID REGION REPO IMAGE_NAME
IMAGE_TAG   := latest
IMAGE       := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(REPO)/$(IMAGE_NAME):$(IMAGE_TAG)

# -----------------------------
# Targets
# -----------------------------
.PHONY: all build deploy url secrets grant-secrets set-url clean

# Build and push the Docker image for Cloud Run (amd64)
build:
	docker buildx build \
		--platform linux/amd64 \
		-t $(IMAGE) \
		--push .

# Deploy to Cloud Run.
# On first deploy APP_BASE_URL is a placeholder — run `make set-url` afterwards.
deploy:
	gcloud run deploy $(IMAGE_NAME) \
		--project $(PROJECT_ID) \
		--image $(IMAGE) \
		--platform managed \
		--region $(REGION) \
		--port 8080 \
		--memory 512Mi \
		--cpu 2 \
		--timeout 1200 \
		--concurrency 80 \
		--allow-unauthenticated \
		--set-secrets GOOGLE_API_KEY=diabuddy-google-api-key:latest,GOOGLE_OAUTH_CLIENT_ID=diabuddy-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=diabuddy-oauth-client-secret:latest,ALLOWED_EMAILS=diabuddy-allowed-emails:latest \
		--set-env-vars APP_BASE_URL=placeholder

# Update APP_BASE_URL on the running service to the stable Cloud Run URL.
# Constructed from project number to avoid the hash-based internal URL.
set-url:
	$(eval PROJECT_NUMBER := $(shell gcloud projects describe $(PROJECT_ID) --format='value(projectNumber)'))
	$(eval URL := https://$(IMAGE_NAME)-$(PROJECT_NUMBER).$(REGION).run.app)
	@echo "Setting APP_BASE_URL to $(URL)"
	gcloud run services update $(IMAGE_NAME) \
		--project $(PROJECT_ID) \
		--region $(REGION) \
		--update-env-vars APP_BASE_URL=$(URL)

# Print the live service URL
url:
	@gcloud run services describe $(IMAGE_NAME) \
		--project $(PROJECT_ID) \
		--region $(REGION) \
		--format='value(status.url)'

# Convenience: build, deploy, then fix the APP_BASE_URL
all: build deploy set-url

# ---------------------------------------------------------------------------
# One-time setup helpers
# ---------------------------------------------------------------------------

# Create secrets in Secret Manager from your local .env file.
# Usage: make secrets
secrets:
	@set -a && source .env && set +a && \
	_upsert_secret() { \
	  local name=$$1 value=$$2; \
	  if gcloud secrets describe $$name --project $(PROJECT_ID) &>/dev/null; then \
	    printf '%s' "$$value" | gcloud secrets versions add $$name \
	      --project $(PROJECT_ID) --data-file=-; \
	  else \
	    printf '%s' "$$value" | gcloud secrets create $$name \
	      --project $(PROJECT_ID) --replication-policy automatic --data-file=-; \
	  fi; \
	}; \
	_upsert_secret diabuddy-google-api-key         "$$GOOGLE_API_KEY"; \
	_upsert_secret diabuddy-oauth-client-id        "$$GOOGLE_OAUTH_CLIENT_ID"; \
	_upsert_secret diabuddy-oauth-client-secret    "$$GOOGLE_OAUTH_CLIENT_SECRET"; \
	_upsert_secret diabuddy-allowed-emails         "$$ALLOWED_EMAILS"
	@echo ""
	@echo "Secrets created. Next run: make grant-secrets"

# Grant the Cloud Run default Compute service account access to the secrets.
# Usage: make grant-secrets
grant-secrets:
	$(eval PROJECT_NUMBER := $(shell gcloud projects describe $(PROJECT_ID) \
		--format='value(projectNumber)'))
	$(eval SA := $(PROJECT_NUMBER)-compute@developer.gserviceaccount.com)
	@echo "Granting $(SA) access to secrets …"
	@for secret in diabuddy-google-api-key diabuddy-oauth-client-id \
	               diabuddy-oauth-client-secret diabuddy-allowed-emails; do \
	  gcloud secrets add-iam-policy-binding $$secret \
	    --project $(PROJECT_ID) \
	    --member "serviceAccount:$(SA)" \
	    --role "roles/secretmanager.secretAccessor"; \
	done
	@echo "Done."

# Clean local docker image
clean:
	docker rmi $(IMAGE) || true
