#!/bin/bash
# HeavySwarm Production Deployment Script
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="heavyswarm-diligence"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check env file
    if [ ! -f "$ENV_FILE" ]; then
        log_error "Environment file $ENV_FILE not found"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Generate SSL certificates (self-signed for initial setup)
generate_ssl_certs() {
    log_info "Generating SSL certificates..."
    
    SSL_DIR="config/nginx/ssl"
    mkdir -p "$SSL_DIR"
    
    if [ ! -f "$SSL_DIR/cert.pem" ] || [ ! -f "$SSL_DIR/key.pem" ]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$SSL_DIR/key.pem" \
            -out "$SSL_DIR/cert.pem" \
            -subj "/C=US/ST=State/L=City/O=HeavySwarm/CN=heavyswarm.io"
        log_success "Self-signed SSL certificates generated"
        log_warning "Replace with proper certificates from Let's Encrypt or your CA for production"
    else
        log_info "SSL certificates already exist"
    fi
}

# Build and deploy
build_and_deploy() {
    log_info "Building and deploying HeavySwarm Due Diligence Engine..."
    
    # Pull latest images
    log_info "Pulling latest base images..."
    docker-compose -f "$COMPOSE_FILE" pull
    
    # Build application images
    log_info "Building application images..."
    docker-compose -f "$COMPOSE_FILE" build --no-cache
    
    # Start services
    log_info "Starting services..."
    docker-compose -f "$COMPOSE_FILE" up -d
    
    log_success "Deployment started"
}

# Wait for services
wait_for_services() {
    log_info "Waiting for services to be healthy..."
    
    # Wait for database
    log_info "Waiting for database..."
    until docker-compose -f "$COMPOSE_FILE" exec -T db pg_isready -U diligence_prod; do
        sleep 2
    done
    log_success "Database is ready"
    
    # Wait for Redis
    log_info "Waiting for Redis..."
    until docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping | grep -q PONG; do
        sleep 2
    done
    log_success "Redis is ready"
    
    # Wait for API
    log_info "Waiting for API..."
    until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
        sleep 2
    done
    log_success "API is ready"
}

# Run migrations
run_migrations() {
    log_info "Running database migrations..."
    docker-compose -f "$COMPOSE_FILE" run --rm migrate
    log_success "Migrations completed"
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."
    
    # Check health endpoint
    HEALTH_STATUS=$(curl -s http://localhost:8000/health | jq -r '.status' 2>/dev/null || echo "error")
    
    if [ "$HEALTH_STATUS" = "healthy" ]; then
        log_success "Health check passed"
    else
        log_error "Health check failed"
        return 1
    fi
    
    # Check all services
    log_info "Service status:"
    docker-compose -f "$COMPOSE_FILE" ps
    
    log_success "Deployment verification completed"
}

# Display status
display_status() {
    echo ""
    echo "================================================================================"
    echo "                    HeavySwarm Deployment Status"
    echo "================================================================================"
    echo ""
    
    docker-compose -f "$COMPOSE_FILE" ps
    
    echo ""
    echo "Access Points:"
    echo "  - API:        https://localhost/api/v1/"
    echo "  - Health:     https://localhost/health"
    echo "  - Prometheus: http://localhost:9090 (localhost only)"
    echo "  - Grafana:    http://localhost:3000 (localhost only)"
    echo ""
    echo "Useful Commands:"
    echo "  - View logs:  docker-compose -f $COMPOSE_FILE logs -f"
    echo "  - Scale API:  docker-compose -f $COMPOSE_FILE up -d --scale api=3"
    echo "  - Stop:       docker-compose -f $COMPOSE_FILE down"
    echo "  - Restart:    docker-compose -f $COMPOSE_FILE restart"
    echo ""
    echo "================================================================================"
}

# Rollback function
rollback() {
    log_warning "Rolling back deployment..."
    docker-compose -f "$COMPOSE_FILE" down
    log_info "Rollback completed. Previous version can be redeployed."
}

# Main deployment flow
main() {
    case "${1:-deploy}" in
        deploy)
            check_prerequisites
            generate_ssl_certs
            build_and_deploy
            wait_for_services
            run_migrations
            verify_deployment
            display_status
            ;;
        status)
            display_status
            ;;
        rollback)
            rollback
            ;;
        migrate)
            run_migrations
            ;;
        verify)
            verify_deployment
            ;;
        *)
            echo "Usage: $0 {deploy|status|rollback|migrate|verify}"
            exit 1
            ;;
    esac
}

main "$@"
