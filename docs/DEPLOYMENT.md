# Deployment Guide

## Production Checklist

- [ ] Set strong `SECRET_KEY` (64+ random bytes)
- [ ] Use managed PostgreSQL (RDS, Cloud SQL, etc.)
- [ ] Enable HTTPS via reverse proxy (nginx, Caddy, Traefik)
- [ ] Set `CORS_ORIGINS` to production domain only
- [ ] Configure Google OAuth redirect URIs
- [ ] Set up log aggregation (CloudWatch, Datadog)
- [ ] Enable database backups
- [ ] Use secrets manager for credentials

## Docker Compose Production

```yaml
# docker-compose.prod.yml overlay
services:
  backend:
    environment:
      DEBUG: "false"
    deploy:
      replicas: 2
  frontend:
    environment:
      VITE_API_URL: https://api.yourdomain.com/api/v1
```

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Environment Variables (Production)

```env
SECRET_KEY=<generate-with-openssl-rand-hex-32>
DATABASE_URL=postgresql+asyncpg://user:pass@db-host:5432/noverep
CORS_ORIGINS=https://app.yourdomain.com
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

## Scaling

- **Backend**: Stateless – scale horizontally behind load balancer
- **PostgreSQL**: Read replicas for statistics queries
- **Redis**: Session cache, rate limit storage, recommendation cache

## Health Monitoring

```bash
curl https://api.yourdomain.com/health
```

Expected: `{"status":"ok","database":"healthy","version":"1.0.0"}`

## Database Migrations

For production schema changes, use Alembic:

```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

Initial deploy uses auto-create via SQLAlchemy metadata.
