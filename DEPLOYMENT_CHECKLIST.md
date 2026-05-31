# HeavySwarm Production Deployment Checklist

## Version 1.0.0

Use this checklist to ensure a complete and successful deployment.

---

## Phase 1: Pre-Deployment Preparation

### Environment Setup

- [ ] Provision production server (4+ cores, 8GB+ RAM, 50GB+ storage)
- [ ] Install Docker 24.0+ and Docker Compose 2.20+
- [ ] Configure firewall (ports 80, 443 open)
- [ ] Set up domain name and DNS records
- [ ] Configure SSL certificates (Let's Encrypt recommended)

### Configuration Files

- [ ] Copy `.env.production` to `.env.production.local`
- [ ] Generate and set `SECRET_KEY` (256-bit random)
- [ ] Set strong `DB_PASSWORD`
- [ ] Set strong `REDIS_PASSWORD`
- [ ] Configure all API keys:
  - [ ] `OPENAI_API_KEY`
  - [ ] `ANTHROPIC_API_KEY`
  - [ ] `XAI_API_KEY`
  - [ ] `ALPHA_VANTAGE_API_KEY`
  - [ ] `NEWSAPI_KEY`
- [ ] Set `TRADING_WEBHOOK_SECRET`
- [ ] Configure `TRADING_WEBHOOK_URL` (if applicable)
- [ ] Set `SENTRY_DSN` (optional but recommended)

### SSL/TLS Setup

- [ ] Place SSL certificate at `config/nginx/ssl/cert.pem`
- [ ] Place SSL private key at `config/nginx/ssl/key.pem`
- [ ] Verify certificate chain is complete
- [ ] Test certificate with: `openssl x509 -in cert.pem -text -noout`

### Directory Structure

- [ ] Create `backups/` directory
- [ ] Create `secrets/` directory
- [ ] Set proper permissions on secrets directory (chmod 700)
- [ ] Verify `config/nginx/ssl/` exists
- [ ] Verify `config/redis/` exists

---

## Phase 2: Docker Build

### Image Building

- [ ] Run: `docker build -t heavyswarm-diligence:1.0.0 --target production .`
- [ ] Verify build completes without errors
- [ ] Check image size is reasonable (< 1GB)
- [ ] Tag image for registry (if using): `docker tag heavyswarm-diligence:1.0.0 <registry>/heavyswarm-diligence:1.0.0`

### Security Scanning

- [ ] Run Trivy scan: `trivy image heavyswarm-diligence:1.0.0`
- [ ] Review and address any CRITICAL or HIGH vulnerabilities
- [ ] Run Docker Scout scan: `docker scout cves heavyswarm-diligence:1.0.0`
- [ ] Document any accepted risks

---

## Phase 3: Infrastructure Deployment

### Initial Startup

- [ ] Run: `./scripts/deploy.sh deploy`
- [ ] Verify all containers start without errors
- [ ] Check service status: `docker-compose -f docker-compose.prod.yml ps`

### Database Setup

- [ ] Verify PostgreSQL container is healthy
- [ ] Run migrations: `docker-compose -f docker-compose.prod.yml run --rm migrate`
- [ ] Verify migrations complete successfully
- [ ] Check database tables exist
- [ ] Verify database user permissions

### Cache Setup

- [ ] Verify Redis container is healthy
- [ ] Test Redis connectivity: `docker-compose -f docker-compose.prod.yml exec redis redis-cli ping`
- [ ] Verify Redis AUTH is working (if configured)

### Nginx/SSL

- [ ] Verify Nginx container is running
- [ ] Test HTTP to HTTPS redirect: `curl -I http://localhost`
- [ ] Test HTTPS connection: `curl -k https://localhost/health`
- [ ] Verify SSL certificate is valid
- [ ] Check security headers are present

---

## Phase 4: Verification

### Health Checks

- [ ] Health endpoint returns 200: `curl https://localhost/health`
- [ ] Response contains `"status": "healthy"`
- [ ] Response contains `"version": "1.0.0"`
- [ ] All subsystems report "ok"

### API Tests

- [ ] Root endpoint accessible: `curl https://localhost/`
- [ ] API docs disabled in production (return 404)
- [ ] Test authentication (if configured)
- [ ] Test rate limiting is active

### End-to-End Tests

- [ ] Run: `./scripts/verify-deployment.sh`
- [ ] All tests pass
- [ ] Document any warnings

### Monitoring

- [ ] Prometheus accessible at http://localhost:9090
- [ ] All targets are UP in Prometheus
- [ ] Grafana accessible at http://localhost:3000
- [ ] Login with admin credentials works
- [ ] HeavySwarm dashboard is visible
- [ ] Metrics are being collected

---

## Phase 5: Security Hardening

### Access Control

- [ ] Change default Grafana password
- [ ] Verify API authentication is enabled
- [ ] Check webhook secret is configured
- [ ] Review exposed ports: `docker-compose -f docker-compose.prod.yml ps`
- [ ] Verify only necessary ports are exposed

### Secrets Management

- [ ] All secrets are in `.env.production.local` (not in git)
- [ ] secrets/ directory has restricted permissions (700)
- [ ] SSL key has restricted permissions (600)
- [ ] No hardcoded secrets in code

### Network Security

- [ ] Firewall rules configured
- [ ] Internal services not exposed externally
- [ ] Prometheus and Grafana bound to localhost only
- [ ] Rate limiting is active

### SSL/TLS

- [ ] TLS 1.2+ only (no TLS 1.0/1.1)
- [ ] Strong cipher suites configured
- [ ] HSTS headers enabled
- [ ] Certificate chain is complete

---

## Phase 6: Backup & Recovery

### Backup Configuration

- [ ] Backup directory exists and is writable
- [ ] Backup script is executable
- [ ] Automated backups configured (cron job)
- [ ] Backup retention policy set (default: 30 days)

### Recovery Testing

- [ ] Document restore procedure
- [ ] Test restore from backup (on test instance)
- [ ] Verify data integrity after restore
- [ ] Document RTO (Recovery Time Objective)
- [ ] Document RPO (Recovery Point Objective)

---

## Phase 7: Documentation

### Operational Documentation

- [ ] DEPLOYMENT.md is complete and accurate
- [ ] RUNBOOK.md is accessible to operators
- [ ] Emergency contact information is current
- [ ] Escalation procedures are documented

### Runbook Verification

- [ ] Daily check procedures documented
- [ ] Alert response procedures documented
- [ ] Rollback procedures documented
- [ ] Emergency procedures documented

---

## Phase 8: Go-Live

### Final Checks

- [ ] All acceptance criteria met
- [ ] Load testing completed (if applicable)
- [ ] Security scan passed
- [ ] Performance benchmarks met
- [ ] Monitoring alerts configured
- [ ] On-call rotation established

### Sign-Off

- [ ] Engineering Lead sign-off
- [ ] Security Team sign-off (if applicable)
- [ ] Operations Team sign-off
- [ ] Business Owner sign-off

### Launch

- [ ] Announce deployment window
- [ ] Execute deployment
- [ ] Verify all systems operational
- [ ] Send go-live notification
- [ ] Monitor for 24 hours post-launch

---

## Post-Deployment

### Immediate (First Hour)

- [ ] Monitor error rates
- [ ] Check response times
- [ ] Verify logs are flowing
- [ ] Confirm backups are running

### First Day

- [ ] Review monitoring dashboards
- [ ] Check resource utilization
- [ ] Verify no security alerts
- [ ] Document any issues

### First Week

- [ ] Performance review
- [ ] Capacity planning review
- [ ] Update documentation with lessons learned
- [ ] Schedule first maintenance window

---

## Rollback Criteria

**Immediate rollback required if:**

- [ ] Error rate exceeds 5%
- [ ] Response time exceeds 10 seconds
- [ ] Database corruption detected
- [ ] Security breach suspected
- [ ] Data loss detected

**Rollback procedure:**

```bash
./scripts/deploy.sh rollback
```

---

## Sign-Off Sheet

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Deployed By | | | |
| Verified By | | | |
| Engineering Lead | | | |
| Operations Lead | | | |

---

## Notes

Document any deviations from standard procedure, issues encountered, or special configurations:

```
[Space for notes]







```

---

**Deployment Complete**: ☐ Yes ☐ No (with exceptions)

**Date Completed**: _______________

**Next Review Date**: _______________
