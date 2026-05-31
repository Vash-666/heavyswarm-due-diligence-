# HeavySwarm Investment Due Diligence Engine - Production Deployment Guide

## Version 1.0.0

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Production Environment Setup](#production-environment-setup)
4. [Docker Production Build](#docker-production-build)
5. [Infrastructure Deployment](#infrastructure-deployment)
6. [Database Migration](#database-migration)
7. [Verification](#verification)
8. [Monitoring & Alerting](#monitoring--alerting)
9. [Backup & Recovery](#backup--recovery)
10. [Rollback Procedures](#rollback-procedures)
11. [Troubleshooting](#troubleshooting)
12. [Security Checklist](#security-checklist)

---

## Prerequisites

### System Requirements

- **OS**: Linux (Ubuntu 22.04 LTS recommended) or macOS
- **Docker**: 24.0+ with BuildKit enabled
- **Docker Compose**: 2.20+
- **CPU**: 4+ cores recommended
- **RAM**: 8GB+ recommended
- **Storage**: 50GB+ available

### Required Tools

```bash
# Verify installations
docker --version
docker-compose --version
openssl version
jq --version
```

### Network Requirements

- Ports 80 and 443 open for web traffic
- Port 9090 for Prometheus (localhost only recommended)
- Port 3000 for Grafana (localhost only recommended)
- Outbound HTTPS for API calls

---

## Quick Start

For experienced operators, the deployment can be done in one command:

```bash
# 1. Clone and enter directory
cd /path/to/HEAVY_SWARM_DUE_DILIGENCE

# 2. Configure environment
cp .env.production .env.production.local
# Edit .env.production.local with your secrets

# 3. Deploy
./scripts/deploy.sh deploy

# 4. Verify
curl https://localhost/health
```

---

## Production Environment Setup

### 1. Environment Configuration

Copy the production environment template:

```bash
cp .env.production .env.production.local
```

Edit `.env.production.local` and set the following required values:

#### Required Secrets

```bash
# Generate a strong secret key (256-bit)
SECRET_KEY=$(openssl rand -hex 32)
echo "SECRET_KEY=$SECRET_KEY"

# Database credentials
DB_PASSWORD=$(openssl rand -base64 32)
echo "DB_PASSWORD=$DB_PASSWORD"

# Redis password
REDIS_PASSWORD=$(openssl rand -base64 24)
echo "REDIS_PASSWORD=$REDIS_PASSWORD"

# Trading webhook secret
TRADING_WEBHOOK_SECRET=$(openssl rand -hex 32)
echo "TRADING_WEBHOOK_SECRET=$TRADING_WEBHOOK_SECRET"
```

#### API Keys

Ensure all API keys are valid:

- `OPENAI_API_KEY` - OpenAI API access
- `ANTHROPIC_API_KEY` - Anthropic Claude access
- `XAI_API_KEY` - xAI/Grok access
- `ALPHA_VANTAGE_API_KEY` - Financial data
- `NEWSAPI_KEY` - News data

### 2. SSL/TLS Certificates

#### Option A: Self-Signed (Development/Testing)

```bash
./scripts/deploy.sh
# Automatically generates self-signed certificates
```

#### Option B: Let's Encrypt (Production)

```bash
# Install certbot
sudo apt-get install certbot

# Generate certificates
sudo certbot certonly --standalone -d your-domain.com

# Copy to nginx ssl directory
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem config/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem config/nginx/ssl/key.pem

# Set up auto-renewal
echo "0 12 * * * /usr/bin/certbot renew --quiet" | sudo crontab -
```

#### Option C: Custom CA Certificates

```bash
# Place your certificates in:
config/nginx/ssl/cert.pem    # Certificate chain
config/nginx/ssl/key.pem     # Private key
```

### 3. Directory Structure

Ensure the following directories exist:

```
HEAVY_SWARM_DUE_DILIGENCE/
├── backups/              # Database backups
├── config/
│   ├── nginx/
│   │   ├── nginx.conf
│   │   └── ssl/         # SSL certificates
│   ├── redis/
│   │   └── redis.conf
│   ├── grafana/
│   │   ├── dashboards/
│   │   └── datasources/
│   └── prometheus.yml
├── secrets/             # Sensitive files (not in git)
│   └── grafana_admin_password.txt
├── scripts/
│   ├── deploy.sh
│   └── backup.sh
├── docker-compose.prod.yml
└── .env.production.local
```

---

## Docker Production Build

### Multi-Stage Build

The Dockerfile uses multi-stage builds for optimization:

```bash
# Build production image
docker build -t heavyswarm-diligence:1.0.0 --target production .

# Tag for registry (if using)
docker tag heavyswarm-diligence:1.0.0 your-registry.com/heavyswarm-diligence:1.0.0
docker push your-registry.com/heavyswarm-diligence:1.0.0
```

### Security Scanning

```bash
# Scan with Trivy
trivy image heavyswarm-diligence:1.0.0

# Scan with Docker Scout
docker scout cves heavyswarm-diligence:1.0.0
```

### Image Optimization

The production image is optimized with:

- **Python 3.11 slim** base image
- **Non-root user** (`appuser`)
- **Multi-stage build** (smaller final image)
- **No dev dependencies** in production
- **Health checks** built-in
- **Security headers** configured

---

## Infrastructure Deployment

### Docker Compose Production Stack

The `docker-compose.prod.yml` defines the following services:

| Service | Description | Replicas | Resources |
|---------|-------------|----------|-----------|
| nginx | Reverse proxy with SSL | 1 | 0.5 CPU, 256MB |
| api | FastAPI application | 2 | 2 CPU, 2GB each |
| worker | Background job processor | 3 | 1 CPU, 1GB each |
| migrate | Database migrations | 1 (run once) | - |
| db | PostgreSQL 15 | 1 | 2 CPU, 2GB |
| redis | Redis 7 cache | 1 | 0.5 CPU, 512MB |
| prometheus | Metrics collection | 1 | 0.5 CPU, 512MB |
| grafana | Dashboards | 1 | 0.5 CPU, 256MB |
| backup | Automated backups | 1 | - |

### Deployment Commands

```bash
# Full deployment
./scripts/deploy.sh deploy

# Or manual steps:

# 1. Build images
docker-compose -f docker-compose.prod.yml build

# 2. Start infrastructure
docker-compose -f docker-compose.prod.yml up -d db redis

# 3. Run migrations
docker-compose -f docker-compose.prod.yml run --rm migrate

# 4. Start application
docker-compose -f docker-compose.prod.yml up -d api worker nginx

# 5. Start monitoring
docker-compose -f docker-compose.prod.yml up -d prometheus grafana
```

### Scaling

```bash
# Scale API instances
docker-compose -f docker-compose.prod.yml up -d --scale api=4

# Scale workers
docker-compose -f docker-compose.prod.yml up -d --scale worker=5
```

---

## Database Migration

### Initial Migration

Migrations run automatically during deployment. To run manually:

```bash
# Run all pending migrations
docker-compose -f docker-compose.prod.yml run --rm migrate

# Check migration status
docker-compose -f docker-compose.prod.yml exec db psql -U diligence_prod -d diligence_prod -c "SELECT * FROM alembic_version;"
```

### Schema Verification

```bash
# Connect to database
docker-compose -f docker-compose.prod.yml exec db psql -U diligence_prod -d diligence_prod

# List tables
\dt

# Verify key tables
SELECT COUNT(*) FROM diligence_requests;
SELECT COUNT(*) FROM diligence_results;
```

### Seeding Initial Data (Optional)

```bash
# If seed data is needed
docker-compose -f docker-compose.prod.yml exec api python -m heavyswarm.seed_data
```

---

## Verification

### Health Endpoint Check

```bash
# Basic health check
curl https://localhost/health

# Expected response:
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00Z",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "llm_clients": "ok"
  }
}
```

### API Smoke Tests

```bash
# Test API root
curl https://localhost/

# Test diligence endpoint (requires auth)
curl -X POST https://localhost/api/v1/diligence \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "ticker": "AAPL",
    "phases": ["research", "financial", "risk"]
  }'

# Test webhook endpoint
curl -X POST https://localhost/api/v1/webhooks/trading \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: YOUR_SECRET" \
  -d '{
    "event": "test",
    "data": {"message": "Hello"}
  }'
```

### End-to-End Workflow Test

```bash
# Run the E2E test suite
docker-compose -f docker-compose.prod.yml exec api python -m pytest tests/e2e/ -v
```

### Monitoring Dashboard Verification

1. **Prometheus**: http://localhost:9090
   - Navigate to Status > Targets
   - Verify all targets are UP

2. **Grafana**: http://localhost:3000
   - Login with admin credentials
   - Check HeavySwarm dashboard is loaded
   - Verify data is flowing

---

## Monitoring & Alerting

### Metrics Available

| Metric | Description | Type |
|--------|-------------|------|
| `diligence_requests_total` | Total diligence requests | Counter |
| `diligence_duration_seconds` | Request duration | Histogram |
| `diligence_active_count` | Active diligences | Gauge |
| `llm_calls_total` | LLM API calls | Counter |
| `llm_errors_total` | LLM errors | Counter |
| `cache_hits_total` | Cache hits | Counter |
| `cache_misses_total` | Cache misses | Counter |

### Key Alerts

```yaml
# Example alert rules (add to prometheus/rules/alerts.yml)
groups:
  - name: heavyswarm
    rules:
      - alert: HighErrorRate
        expr: rate(diligence_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          
      - alert: DatabaseDown
        expr: up{job="postgresql"} == 0
        for: 1m
        labels:
          severity: critical
```

### Log Aggregation

```bash
# View all logs
docker-compose -f docker-compose.prod.yml logs -f

# View specific service
docker-compose -f docker-compose.prod.yml logs -f api

# View with timestamp
docker-compose -f docker-compose.prod.yml logs -f --timestamps api
```

---

## Backup & Recovery

### Automated Backups

Backups run automatically daily at 2 AM. Configuration:

```bash
# Backup retention (default: 30 days)
BACKUP_RETENTION_DAYS=30

# Manual backup
docker-compose -f docker-compose.prod.yml exec backup /backup.sh
```

### Backup Files

Backups are stored in `./backups/`:

```
backups/
├── diligence_backup_20240115_020000.sql.gz
├── diligence_backup_20240114_020000.sql.gz
└── ...
```

### Restore from Backup

```bash
# 1. Stop application
docker-compose -f docker-compose.prod.yml stop api worker

# 2. Restore database
docker-compose -f docker-compose.prod.yml exec -T db psql -U diligence_prod < <(gunzip -c backups/diligence_backup_20240115_020000.sql.gz)

# 3. Restart application
docker-compose -f docker-compose.prod.yml start api worker
```

### Disaster Recovery

```bash
# Full system restore

# 1. Stop all services
docker-compose -f docker-compose.prod.yml down

# 2. Restore volumes from backup
# (Use your backup solution: restic, duplicity, etc.)

# 3. Restore database
docker-compose -f docker-compose.prod.yml up -d db
docker-compose -f docker-compose.prod.yml exec -T db psql -U diligence_prod < backup.sql

# 4. Start all services
docker-compose -f docker-compose.prod.yml up -d
```

---

## Rollback Procedures

### Quick Rollback

```bash
# Rollback to previous version
./scripts/deploy.sh rollback

# Or manually:
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
```

### Database Rollback

```bash
# Rollback one migration
docker-compose -f docker-compose.prod.yml run --rm migrate alembic downgrade -1

# Rollback to specific version
docker-compose -f docker-compose.prod.yml run --rm migrate alembic downgrade <revision>
```

### Emergency Procedures

```bash
# Stop all traffic
 docker-compose -f docker-compose.prod.yml stop nginx

# Scale down workers
docker-compose -f docker-compose.prod.yml up -d --scale worker=0

# Database maintenance mode
docker-compose -f docker-compose.prod.yml exec db psql -U diligence_prod -c "REVOKE CONNECT ON DATABASE diligence_prod FROM PUBLIC;"
```

---

## Troubleshooting

### Common Issues

#### Service Won't Start

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs <service>

# Check resource usage
docker stats

# Restart service
docker-compose -f docker-compose.prod.yml restart <service>
```

#### Database Connection Issues

```bash
# Test database connectivity
docker-compose -f docker-compose.prod.yml exec api python -c "import asyncpg; print('OK')"

# Check database logs
docker-compose -f docker-compose.prod.yml logs db
```

#### High Memory Usage

```bash
# Check memory usage
docker stats --no-stream

# Restart services
docker-compose -f docker-compose.prod.yml restart api worker
```

#### SSL Certificate Issues

```bash
# Verify certificate
openssl x509 -in config/nginx/ssl/cert.pem -text -noout

# Test SSL connection
curl -v https://localhost
```

### Debug Mode

```bash
# Run with debug logging
LOG_LEVEL=DEBUG docker-compose -f docker-compose.prod.yml up -d

# Interactive shell in container
docker-compose -f docker-compose.prod.yml exec api /bin/sh
```

---

## Security Checklist

### Pre-Deployment

- [ ] Changed default passwords (DB, Redis, Grafana)
- [ ] Generated strong SECRET_KEY
- [ ] Configured SSL/TLS certificates
- [ ] Set up firewall rules
- [ ] Disabled debug mode
- [ ] Reviewed API key permissions
- [ ] Enabled audit logging

### Post-Deployment

- [ ] Verified SSL configuration (SSL Labs test)
- [ ] Tested authentication
- [ ] Verified rate limiting
- [ ] Checked security headers
- [ ] Reviewed exposed ports
- [ ] Set up log monitoring
- [ ] Configured automated backups
- [ ] Tested disaster recovery

### Ongoing

- [ ] Regular security updates
- [ ] Rotate API keys quarterly
- [ ] Review access logs
- [ ] Test backup restoration
- [ ] Update SSL certificates
- [ ] Security scanning

---

## Support

For issues and questions:

- **Documentation**: See README.md and docs/
- **Issues**: Check GitHub Issues
- **Email**: team@heavyswarm.io

---

## Changelog

### v1.0.0 (2024-01-15)

- Initial production release
- 7-agent multi-phase analysis system
- Quality Guardian integration
- Full monitoring and alerting
- Production-ready Docker setup

---

**End of Deployment Guide**
