# DiaBuddy

Just a simple helper guide project built for my lovely fianceé. When managing insulin dosage gets difficult on the go, this tool can be very useful!

It's an AI-powered insulin dosage assistant agent for Type 1 diabetes, built with Google ADK, FastAPI, and Streamlit. Deployed on Cloud Run behind nginx.

---

## How it works

1. Patient signs in via Google OAuth. (access managed with .env by adding google account email ids)
2. Describes what they're gonna eat and the pre-meal blood sugar level in mg/dl
3. A 3-step ADK agent pipeline (recipe → carb → insulin) calculates the Apidra dose. (an estimated guess, backed by some calculations)
4. Result is shown in the Streamlit UI.

<img width="2816" height="1536" alt="Gemini_Generated_Image_nhx1x2nhx1x2nhx1" src="https://github.com/user-attachments/assets/40d20443-d6e1-46a3-918b-ffaa0757e16c" />

---

## Prerequisites

- Docker with buildx
- `gcloud` CLI authenticated (`gcloud auth login`)
- A Google Cloud project with billing enabled
- An Artifact Registry repository for Docker images
- A Google Cloud OAuth 2.0 client ID (Web application type)
- A Gemini API key

---

## One-time GCP setup

### 1. Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  --project YOUR_PROJECT_ID
```

### 2. Configure the Makefile

Edit the top of `Makefile` to match your project:

```makefile
PROJECT_ID  := your-gcp-project-id
REGION      := your-region          # e.g. asia-south1
REPO        := your-artifact-repo   # Artifact Registry repo name
IMAGE_NAME  := your-image-name
```

### 3. Create your `.env` file

```bash
cp .env-example .env
# fill in your real values
```

### 4. Push secrets to Secret Manager

```bash
make secrets
make grant-secrets
```

### 5. Configure Google OAuth

In **Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID**, add the following to **Authorized redirect URIs**:

- `http://localhost:8080/auth/callback` (for local dev)
- `https://YOUR_CLOUD_RUN_URL/auth/callback` (added automatically after first deploy via `make all`)

---

## Local development

```bash
# Build and run locally (mirrors the Cloud Run container exactly)
docker build -t diabuddy .
docker run --env-file .env -p 8080:8080 diabuddy

# Open in browser
open http://localhost:8080
```

Useful flags:

```bash
# Run in background
docker run --env-file .env -p 8080:8080 -d --name diabuddy diabuddy

# Tail logs
docker logs -f diabuddy

# Stop and remove
docker stop diabuddy && docker rm diabuddy
```

---

## Deploy to Cloud Run

```bash
make all
```

This builds the Docker image, pushes it to Artifact Registry, deploys to Cloud Run, and automatically sets `APP_BASE_URL` to the live service URL.

After the first deploy, add the printed Cloud Run URL's `/auth/callback` to your OAuth client's authorized redirect URIs.

---

## Make targets

| Target | Description |
|---|---|
| `make all` | Build + deploy + set URL (full pipeline) |
| `make build` | Build and push the Docker image (linux/amd64) |
| `make deploy` | Deploy the image to Cloud Run |
| `make set-url` | Update `APP_BASE_URL` env var to the live Cloud Run URL |
| `make url` | Print the live service URL |
| `make secrets` | Upsert secrets from `.env` into Secret Manager |
| `make grant-secrets` | Grant the Cloud Run service account access to secrets |
| `make clean` | Remove the local Docker image |

---

## Architecture

```
Internet
   │
   ▼
nginx :8080
   ├── /auth/*  →  FastAPI (uvicorn) :8000
   ├── /api/*   →  FastAPI (uvicorn) :8000
   └── /*       →  Streamlit :8501
```

All three processes run in a single Cloud Run container managed by `start.sh`. nginx waits for Streamlit to be ready before accepting traffic.
