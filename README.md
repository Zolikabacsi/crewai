# CrewAI Crypto Research Agent

Packaging scaffold for dedicated-hardware deployment and GitHub migration.

## Quick start
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
python scripts/daily_crypto_research.py
```

## Docker
```bash
docker compose build
docker compose up -d
```

## GitHub push
```bash
git status
git add README.md Dockerfile docker-compose.yml
git commit -m "Add deployment scaffolding"
# then push to your existing remote
```
