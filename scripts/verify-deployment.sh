#!/bin/bash
# HeavySwarm Deployment Verification Script
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
COMPOSE_FILE="docker-compose.prod.yml"
BASE_URL="https://localhost"
FAILED=0
PASSED=0

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Test functions
test_prerequisites() {
    log_info "Testing prerequisites..."
    
    if command -v docker &> /dev/null; then
        log_pass "Docker is installed"
    else
        log_fail "Docker is not installed"
    fi
    
    if command -v docker-compose &> /dev/null; then
        log_pass "Docker Compose is installed"
    else
        log_fail "Docker Compose is not installed"
    fi
    
    if [ -f "$COMPOSE_FILE" ]; then
        log_pass "Production compose file exists"
    else
        log_fail "Production compose file not found"
    fi
    
    if [ -f ".env.production" ]; then
        log_pass "Production environment file exists"
    else
        log_fail "Production environment file not found"
    fi
}

test_services_running() {
    log_info "Testing services are running..."
    
    SERVICES=("nginx" "api" "worker" "db" "redis" "prometheus" "grafana")
    
    for service in "${SERVICES[@]}"; do
        if docker-compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
            log_pass "Service $service is running"
        else
            log_fail "Service $service is not running"
        fi
    done
}

test_health_endpoint() {
    log_info "Testing health endpoint..."
    
    if command -v curl &> /dev/null; then
        RESPONSE=$(curl -sk "${BASE_URL}/health" 2>/dev/null)
        
        if echo "$RESPONSE" | grep -q '"status":"healthy"'; then
            log_pass "Health endpoint returns healthy status"
        else
            log_fail "Health endpoint not healthy"
            echo "  Response: $RESPONSE"
        fi
        
        if echo "$RESPONSE" | grep -q '"version":"1.0.0"'; then
            log_pass "API version is 1.0.0"
        else
            log_fail "API version mismatch"
        fi
    else
        log_warn "curl not available, skipping health check"
    fi
}

test_api_endpoints() {
    log_info "Testing API endpoints..."
    
    # Test root endpoint
    RESPONSE=$(curl -sk "${BASE_URL}/" 2>/dev/null)
    if echo "$RESPONSE" | grep -q "HeavySwarm"; then
        log_pass "Root endpoint accessible"
    else
        log_fail "Root endpoint not accessible"
    fi
    
    # Test API docs (should be disabled in production)
    DOCS_RESPONSE=$(curl -sk "${BASE_URL}/docs" -o /dev/null -w "%{http_code}")
    if [ "$DOCS_RESPONSE" = "404" ] || [ "$DOCS_RESPONSE" = "403" ]; then
        log_pass "API docs correctly disabled in production"
    else
        log_warn "API docs may be enabled (status: $DOCS_RESPONSE)"
    fi
}

test_database() {
    log_info "Testing database connectivity..."
    
    if docker-compose -f "$COMPOSE_FILE" exec -T db pg_isready -U diligence_prod &>/dev/null; then
        log_pass "Database is accepting connections"
    else
        log_fail "Database is not accepting connections"
    fi
    
    # Check if tables exist
    TABLE_COUNT=$(docker-compose -f "$COMPOSE_FILE" exec -T db psql -U diligence_prod -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')
    if [ "$TABLE_COUNT" -gt 0 ]; then
        log_pass "Database has $TABLE_COUNT tables"
    else
        log_fail "Database has no tables"
    fi
}

test_redis() {
    log_info "Testing Redis connectivity..."
    
    if docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping | grep -q PONG; then
        log_pass "Redis is responding to PING"
    else
        log_fail "Redis is not responding"
    fi
}

test_ssl() {
    log_info "Testing SSL configuration..."
    
    if command -v openssl &> /dev/null; then
        # Check if certificate exists
        if [ -f "config/nginx/ssl/cert.pem" ]; then
            log_pass "SSL certificate file exists"
            
            # Check certificate expiry
            EXPIRY=$(openssl x509 -in config/nginx/ssl/cert.pem -noout -dates | grep notAfter | cut -d= -f2)
            log_info "Certificate expires: $EXPIRY"
        else
            log_fail "SSL certificate file not found"
        fi
        
        # Test HTTPS connection
        if curl -sk "${BASE_URL}/health" &>/dev/null; then
            log_pass "HTTPS connection successful"
        else
            log_fail "HTTPS connection failed"
        fi
    else
        log_warn "openssl not available, skipping SSL tests"
    fi
}

test_monitoring() {
    log_info "Testing monitoring stack..."
    
    # Test Prometheus
    if curl -s "http://localhost:9090/-/healthy" &>/dev/null; then
        log_pass "Prometheus is healthy"
    else
        log_fail "Prometheus is not healthy"
    fi
    
    # Test Grafana
    if curl -s "http://localhost:3000/api/health" &>/dev/null; then
        log_pass "Grafana is healthy"
    else
        log_fail "Grafana is not healthy"
    fi
}

test_security_headers() {
    log_info "Testing security headers..."
    
    if command -v curl &> /dev/null; then
        HEADERS=$(curl -skI "${BASE_URL}/health" 2>/dev/null)
        
        if echo "$HEADERS" | grep -qi "X-Frame-Options"; then
            log_pass "X-Frame-Options header present"
        else
            log_fail "X-Frame-Options header missing"
        fi
        
        if echo "$HEADERS" | grep -qi "X-Content-Type-Options"; then
            log_pass "X-Content-Type-Options header present"
        else
            log_fail "X-Content-Type-Options header missing"
        fi
    fi
}

test_backup() {
    log_info "Testing backup configuration..."
    
    if [ -d "backups" ]; then
        log_pass "Backup directory exists"
    else
        log_fail "Backup directory not found"
    fi
    
    if [ -f "scripts/backup.sh" ]; then
        log_pass "Backup script exists"
    else
        log_fail "Backup script not found"
    fi
}

test_resources() {
    log_info "Testing resource usage..."
    
    # Check disk space
    DISK_USAGE=$(df -h . | tail -1 | awk '{print $5}' | tr -d '%')
    if [ "$DISK_USAGE" -lt 80 ]; then
        log_pass "Disk usage is ${DISK_USAGE}% (under 80%)"
    else
        log_warn "Disk usage is ${DISK_USAGE}% (over 80%)"
    fi
    
    # Check memory (if docker stats available)
    if docker stats --no-stream &>/dev/null; then
        log_pass "Docker stats available"
    else
        log_warn "Cannot check container resource usage"
    fi
}

# Main
main() {
    echo "================================================================================"
    echo "               HeavySwarm Deployment Verification"
    echo "================================================================================"
    echo ""
    
    test_prerequisites
    test_services_running
    test_health_endpoint
    test_api_endpoints
    test_database
    test_redis
    test_ssl
    test_monitoring
    test_security_headers
    test_backup
    test_resources
    
    echo ""
    echo "================================================================================"
    echo "                          Verification Summary"
    echo "================================================================================"
    echo -e "Tests Passed: ${GREEN}${PASSED}${NC}"
    echo -e "Tests Failed: ${RED}${FAILED}${NC}"
    echo ""
    
    if [ $FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed! Deployment is healthy.${NC}"
        exit 0
    else
        echo -e "${RED}✗ Some tests failed. Please review the output above.${NC}"
        exit 1
    fi
}

main "$@"
