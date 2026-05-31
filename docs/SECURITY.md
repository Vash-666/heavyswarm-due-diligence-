# HeavySwarm Security Guide

## Overview

This document outlines the security measures implemented in HeavySwarm and provides guidance for maintaining a secure deployment.

## Security Checklist

### Authentication & Authorization

- [x] JWT-based authentication implemented
- [x] Token expiration configured (30 minutes default)
- [x] Secure secret key management
- [ ] Regular secret rotation (see procedure below)
- [ ] Multi-factor authentication (MFA) for admin access

### Data Protection

- [x] API keys stored in environment variables
- [x] Database credentials encrypted at rest
- [x] Redis password protection
- [x] No sensitive data in logs
- [ ] Database encryption at rest
- [ ] Backup encryption

### Input Validation

- [x] Pydantic models for request validation
- [x] SQL injection prevention via SQLAlchemy ORM
- [x] XSS prevention via output encoding
- [ ] Rate limiting on all endpoints
- [ ] Content Security Policy headers

### Network Security

- [x] HTTPS-only API access
- [x] CORS configured for production
- [ ] Web Application Firewall (WAF)
- [ ] DDoS protection
- [ ] Network segmentation

### Monitoring & Alerting

- [x] Structured logging with sensitive data redaction
- [x] Prometheus metrics for security events
- [ ] SIEM integration
- [ ] Automated security scanning
- [ ] Intrusion detection system

## JWT Secret Rotation Procedure

### Prerequisites

1. Access to production environment
2. Database backup completed
3. Maintenance window scheduled
4. Rollback plan prepared

### Rotation Steps

1. **Generate New Secret**
   ```bash
   # Run the rotation script
   python scripts/rotate_jwt_secret.py
   ```

2. **Update Environment**
   ```bash
   # Set new secret in environment
   export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
   ```

3. **Rolling Restart**
   - Restart API instances one at a time
   - Verify health checks pass
   - Monitor error rates

4. **Invalidate Old Tokens**
   - Old tokens will expire naturally (30 min)
   - Or force logout all users via admin endpoint

5. **Verification**
   - Test authentication flow
   - Verify new tokens work
   - Check logs for errors

### Rollback Procedure

If issues occur:

1. Restore previous secret from backup
2. Restart all instances
3. Investigate root cause

## Input Validation

### SQL Injection Prevention

HeavySwarm uses SQLAlchemy ORM which provides protection against SQL injection:

```python
# Safe - uses parameterized queries
result = await session.execute(
    select(Diligence).where(Diligence.diligence_id == diligence_id)
)

# Never do this - vulnerable to SQL injection
query = f"SELECT * FROM diligences WHERE id = '{diligence_id}'"
```

### XSS Prevention

All output is properly escaped:

```python
# Safe - Pydantic handles escaping
return {"message": user_input}  # Automatically escaped in JSON

# When rendering HTML, use template escaping
from jinja2 import escape
safe_output = escape(user_input)
```

## Secrets Management

### Required Environment Variables

```bash
# Security
SECRET_KEY=<random-32-byte-string>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# API Keys (rotate quarterly)
OPENAI_API_KEY=<encrypted>
ANTHROPIC_API_KEY=<encrypted>
XAI_API_KEY=<encrypted>
ALPHA_VANTAGE_API_KEY=<encrypted>
NEWSAPI_KEY=<encrypted>

# Database
DATABASE_URL=<encrypted-connection-string>
REDIS_PASSWORD=<encrypted>

# Webhooks
TRADING_WEBHOOK_SECRET=<encrypted>
```

### Secrets Scanning

Run secrets scanning before commits:

```bash
# Install pre-commit hooks
pre-commit install

# Manual scan
git-secrets --scan
```

## Security Headers

The following headers are configured in production:

```python
# Security headers middleware
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response
```

## Vulnerability Disclosure

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. Email security@heavyswarm.io with details
3. Allow 90 days for remediation before public disclosure
4. Include steps to reproduce and potential impact

## Compliance

### Data Retention

- Audit logs: 7 years
- Diligence data: 5 years
- Session logs: 90 days
- Error logs: 30 days

### Access Controls

- Role-based access control (RBAC)
- Principle of least privilege
- Regular access reviews (quarterly)

## Incident Response

### Severity Levels

1. **Critical**: Data breach, unauthorized access
2. **High**: Service disruption, potential data exposure
3. **Medium**: Performance degradation, non-critical vulnerabilities
4. **Low**: Minor issues, cosmetic problems

### Response Procedure

1. **Detect**: Monitoring alerts, user reports
2. **Assess**: Determine severity and scope
3. **Contain**: Isolate affected systems
4. **Investigate**: Root cause analysis
5. **Remediate**: Fix and verify
6. **Communicate**: Notify stakeholders
7. **Review**: Post-incident analysis

## Security Testing

### Automated Scans

```bash
# Dependency vulnerability scan
pip-audit

# Static analysis
bandit -r src/

# Secrets scan
git-secrets --scan
```

### Penetration Testing

- Annual third-party penetration test
- Quarterly internal security review
- Continuous automated scanning

## Contact

- Security Team: security@heavyswarm.io
- Emergency: +1-555-SECURITY
- GPG Key: [Download](https://heavyswarm.io/security.gpg)
