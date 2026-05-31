# HeavySwarm Production Runbook

## Quick Reference for Operators

---

## Daily Checks

### Morning (9 AM)

```bash
# 1. Check system health
curl -s https://localhost/health | jq .

# 2. Check service status
docker-compose -f docker-compose.prod.yml ps

# 3. Check recent errors
docker-compose -f docker-compose.prod.yml logs --since=24h api | grep -i error

# 4. Review metrics
curl -s http://localhost:9090/api/v1/query?query=up | jq .
```

### Evening (6 PM)

```bash
# 1. Check day's activity
docker-compose -f docker-compose.prod.yml exec db psql -U diligence_prod -c "SELECT COUNT(*) FROM diligence_requests WHERE created_at > NOW() - INTERVAL '24 hours';"

# 2. Verify backup from last night
ls -lh backups/diligence_backup_$(date +%Y%m%d)*.sql.gz

# 3. Check disk space
df -h
docker system df
```

---

## Common Operations

### Restart Services

```bash
# Restart all
docker-compose -f docker-compose.prod.yml restart

# Restart specific service
docker-compose -f docker-compose.prod.yml restart api

# Graceful restart (zero downtime for API)
docker-compose -f docker-compose.prod.yml up -d --scale api=3 --no-deps api
docker-compose -f docker-compose.prod.yml up -d --scale api=2 --no-deps api
```

### View Logs

```bash
# Real-time logs
docker-compose -f docker-compose.prod.yml logs -f

# Last 100 lines
docker-compose -f docker-compose.prod.yml logs --tail=100 api

# Specific time range
docker-compose -f docker-compose.prod.yml logs --since=2024-01-15T10:00:00 --until=2024-01-15T11:00:00 api

# Search for errors
docker-compose -f docker-compose.prod.yml logs api | grep -i error
```

### Database Operations

```bash
# Connect to database
docker-compose -f docker-compose.prod.yml exec db psql -U diligence_prod -d diligence_prod

# Common queries:
# Active diligences
SELECT status, COUNT(*) FROM diligence_requests WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY status;

# Error rate
SELECT COUNT(*) FROM diligence_requests WHERE status = 'failed' AND created_at > NOW() - INTERVAL '24 hours';

# Average processing time
SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) FROM diligence_requests WHERE status = 'completed' AND created_at > NOW() - INTERVAL '24 hours';
```

### Scaling

```bash
# Scale up API (during high load)
docker-compose -f docker-compose.prod.yml up -d --scale api=4

# Scale up workers
docker-compose -f docker-compose.prod.yml up -d --scale worker=5

# Scale down (during maintenance)
docker-compose -f docker-compose.prod.yml up -d --scale api=1 --scale worker=1
```

---

## Alert Response

### High Error Rate

**Symptoms**: Alert fires for `rate(diligence_errors_total[5m]) > 0.1`

**Response**:
1. Check logs: `docker-compose -f docker-compose.prod.yml logs -f api`
2. Identify error pattern
3. If LLM errors: Check API key quotas
4. If database errors: Check connection pool
5. If needed: Restart services

### Database Down

**Symptoms**: Alert fires for `up{job="postgresql"} == 0`

**Response**:
1. Check database container: `docker-compose -f docker-compose.prod.yml ps db`
2. Check logs: `docker-compose -f docker-compose.prod.yml logs db`
3. Check disk space: `df -h`
4. Restart if needed: `docker-compose -f docker-compose.prod.yml restart db`
5. If persistent: Check PostgreSQL logs in container

### High Memory Usage

**Symptoms**: Container using >80% memory limit

**Response**:
1. Check usage: `docker stats --no-stream`
2. Identify culprit service
3. Restart service: `docker-compose -f docker-compose.prod.yml restart <service>`
4. If recurring: Review memory limits in docker-compose.prod.yml

---

## Maintenance Windows

### Weekly (Sunday 2 AM)

```bash
# 1. Update images
docker-compose -f docker-compose.prod.yml pull

# 2. Restart with updates
docker-compose -f docker-compose.prod.yml up -d

# 3. Clean up old images
docker image prune -f

# 4. Verify health
curl https://localhost/health
```

### Monthly

```bash
# 1. Full system update
apt-get update && apt-get upgrade -y  # On host

# 2. Update Docker images to latest
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d

# 3. Clean up Docker system
docker system prune -a -f

# 4. Review and rotate secrets
# - API keys
# - Database passwords
# - SSL certificates

# 5. Test backup restoration
# See DEPLOYMENT.md for restore procedure
```

---

## Emergency Procedures

### Complete Outage

1. **Assess**: Check if all services are down
   ```bash
   docker-compose -f docker-compose.prod.yml ps
   ```

2. **Restart**: Full stack restart
   ```bash
   docker-compose -f docker-compose.prod.yml restart
   ```

3. **Verify**: Check all services come up
   ```bash
   curl https://localhost/health
   ```

4. **Escalate**: If still down, check infrastructure (host, network)

### Database Corruption

1. **Stop writes**: `docker-compose -f docker-compose.prod.yml stop api worker`

2. **Assess**: Check PostgreSQL logs
   ```bash
   docker-compose -f docker-compose.prod.yml logs db
   ```

3. **Restore**: From latest backup
   ```bash
   # See DEPLOYMENT.md for full restore procedure
   ```

4. **Verify**: Check data integrity

### Security Incident

1. **Isolate**: Stop public access
   ```bash
   docker-compose -f docker-compose.prod.yml stop nginx
   ```

2. **Assess**: Review logs for intrusion
   ```bash
   docker-compose -f docker-compose.prod.yml logs nginx | grep -i "suspicious"
   ```

3. **Rotate**: All secrets and API keys

4. **Patch**: Update to latest versions

5. **Monitor**: Enhanced logging

---

## Performance Tuning

### Database

```sql
-- Check slow queries
SELECT query, calls, mean_time, total_time 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;

-- Check table bloat
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables 
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Vacuum and analyze
VACUUM ANALYZE;
```

### Cache

```bash
# Check Redis stats
docker-compose -f docker-compose.prod.yml exec redis redis-cli info stats

# Check hit rate
docker-compose -f docker-compose.prod.yml exec redis redis-cli info stats | grep keyspace

# Clear cache if needed
docker-compose -f docker-compose.prod.yml exec redis redis-cli FLUSHDB
```

### API

```bash
# Check response times
curl -w "@curl-format.txt" -o /dev/null -s https://localhost/health

# Load test (use Locust)
locust -f locustfile.py --host=https://localhost
```

---

## Contact Information

| Role | Contact | Escalation |
|------|---------|------------|
| Primary On-Call | ops@heavyswarm.io | +1-555-0100 |
| Engineering Lead | eng@heavyswarm.io | +1-555-0101 |
| Security | security@heavyswarm.io | +1-555-0102 |

---

## Runbook Version

- **Version**: 1.0.0
- **Last Updated**: 2024-01-15
- **Review Cycle**: Monthly

---

**Keep this runbook accessible during all shifts.**
