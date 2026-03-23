#!/usr/bin/env bash
set -euo pipefail

# ══════════════════════════════════════════════════
# Callbot Deploy Script
# Usage: ./deploy.sh [--dry-run] [--skip-build] [--env ENV]
# ══════════════════════════════════════════════════

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()   { echo -e "${BLUE}🔧 $1${NC}"; }
ok()    { echo -e "${GREEN}✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

# Defaults
DRY_RUN=false
SKIP_BUILD=false
ENV="dev"
REGION="ap-northeast-2"
PROJECT="callbot"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)    DRY_RUN=true; shift ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    --env)        ENV="$2"; shift 2 ;;
    --region)     REGION="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: ./deploy.sh [--dry-run] [--skip-build] [--env ENV] [--region REGION]"
      echo ""
      echo "Options:"
      echo "  --dry-run      Show what would be done without executing"
      echo "  --skip-build   Skip Docker build, push existing image"
      echo "  --env ENV      Environment (default: dev)"
      echo "  --region REG   AWS region (default: ap-northeast-2)"
      exit 0 ;;
    *) fail "Unknown option: $1" ;;
  esac
done

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${PROJECT}-${ENV}-api"
ECS_CLUSTER="${PROJECT}-${ENV}"
ECS_SERVICE="${PROJECT}-${ENV}-api"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║       Callbot Deploy Pipeline        ║"
echo "╠══════════════════════════════════════╣"
echo "║  Environment: ${ENV}"
echo "║  Region:      ${REGION}"
echo "║  ECR:         ${ECR_REPO}"
echo "║  Cluster:     ${ECS_CLUSTER}"
echo "║  Dry Run:     ${DRY_RUN}"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Step 1: Preflight Check ─────────────────────

preflight_check() {
  log "Step 1/4: Preflight check..."

  local missing=()
  command -v aws    &>/dev/null || missing+=("aws-cli")
  command -v docker &>/dev/null || missing+=("docker")

  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "Missing tools: ${missing[*]}\nInstall them first. See SETUP.md"
  fi

  # Check AWS credentials
  if ! aws sts get-caller-identity &>/dev/null; then
    fail "AWS credentials not configured. Run 'aws configure' or set AWS_PROFILE"
  fi

  # Check ECR repo exists
  if ! aws ecr describe-repositories --repository-names "${PROJECT}-${ENV}-api" --region "${REGION}" &>/dev/null; then
    fail "ECR repository '${PROJECT}-${ENV}-api' not found.\nRun 'terraform apply' in callbot-infra first."
  fi

  ok "Preflight check passed"
}

# ── Step 2: Build & Push ────────────────────────

build_push() {
  log "Step 2/4: Build & push Docker image..."

  if [[ "$SKIP_BUILD" == "true" ]]; then
    warn "Skipping build (--skip-build)"
    return
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [dry-run] docker build -t ${PROJECT}-${ENV}-api ."
    echo "  [dry-run] docker tag → ${ECR_REPO}:latest"
    echo "  [dry-run] docker push ${ECR_REPO}:latest"
    return
  fi

  # ECR login
  aws ecr get-login-password --region "${REGION}" | \
    docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

  # Build
  docker build -t "${PROJECT}-${ENV}-api" .

  # Tag & Push
  docker tag "${PROJECT}-${ENV}-api:latest" "${ECR_REPO}:latest"
  docker push "${ECR_REPO}:latest"

  ok "Image pushed: ${ECR_REPO}:latest"
}

# ── Step 3: Deploy ECS ──────────────────────────

deploy_ecs() {
  log "Step 3/4: Deploy to ECS..."

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [dry-run] aws ecs update-service --force-new-deployment"
    echo "  [dry-run] aws ecs wait services-stable"
    return
  fi

  aws ecs update-service \
    --cluster "${ECS_CLUSTER}" \
    --service "${ECS_SERVICE}" \
    --force-new-deployment \
    --region "${REGION}" \
    > /dev/null

  log "Waiting for ECS service to stabilize..."
  aws ecs wait services-stable \
    --cluster "${ECS_CLUSTER}" \
    --services "${ECS_SERVICE}" \
    --region "${REGION}"

  ok "ECS deployment complete"
}

# ── Step 4: CloudFront Invalidation ─────────────

invalidate_cf() {
  log "Step 4/4: CloudFront invalidation..."

  # Get distribution ID from Terraform output
  local cf_id=""
  if command -v terraform &>/dev/null; then
    local infra_dir="$(dirname "$0")/../callbot-infra-new/envs/${ENV}/application"
    if [[ -d "$infra_dir" ]]; then
      cf_id=$(cd "$infra_dir" && terraform output -raw cloudfront_distribution_id 2>/dev/null || echo "")
    fi
  fi

  # Fallback: try AWS CLI
  if [[ -z "$cf_id" ]]; then
    cf_id=$(aws cloudfront list-distributions --query \
      "DistributionList.Items[?Comment=='${PROJECT}-${ENV}'].Id | [0]" \
      --output text 2>/dev/null || echo "")
  fi

  if [[ -z "$cf_id" || "$cf_id" == "None" ]]; then
    warn "No CloudFront distribution found. Skipping invalidation."
    return
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [dry-run] aws cloudfront create-invalidation --distribution-id ${cf_id} --paths /demo/* /admin/*"
    return
  fi

  aws cloudfront create-invalidation \
    --distribution-id "${cf_id}" \
    --paths "/demo/*" "/admin/*" \
    --region us-east-1 \
    > /dev/null

  ok "CloudFront invalidation created (${cf_id}): /demo/*, /admin/*"
}

# ── Run ─────────────────────────────────────────

preflight_check
build_push
deploy_ecs
invalidate_cf

echo ""
ok "🎉 Deploy complete!"
echo ""
