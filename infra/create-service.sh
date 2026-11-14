#!/usr/bin/env bash
# Creates the service on Amazon ECS Express Mode (Fargate + load balancer + HTTPS URL, managed by AWS).
# (App Runner is closed to new AWS accounts since 2026-04-30, so we use ECS Express Mode instead.)
# Run AFTER GitHub Actions has pushed the first image to ECR.
#   bash infra/create-service.sh
set -euo pipefail

REGION="${APP_REGION:-ap-northeast-1}"
APP="expert-profile-api"
TABLE="${APP}-history"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
IMAGE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${APP}:latest"
EXEC_ROLE="${APP}-ecs-execution"
TASK_ROLE="${APP}-ecs-task"
INFRA_ROLE="${APP}-ecs-infrastructure"

aws ecr describe-images --repository-name "$APP" --image-ids imageTag=latest --region "$REGION" >/dev/null 2>&1 || {
  echo "No ':latest' image in ECR yet. Run the GitHub Actions workflow and wait for it to finish first."; exit 1; }

trust() {  # service principal -> trust policy JSON
  echo "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"$1\"},\"Action\":\"sts:AssumeRole\"}]}"
}
ensure_role() {  # role-name principal
  aws iam get-role --role-name "$1" >/dev/null 2>&1 || aws iam create-role --role-name "$1" --assume-role-policy-document "$(trust "$2")" >/dev/null
}

echo "== ECS service-linked role (new accounts don't have it yet) =="
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com >/dev/null 2>&1 || true

echo "== IAM roles =="
ensure_role "$EXEC_ROLE" ecs-tasks.amazonaws.com
aws iam attach-role-policy --role-name "$EXEC_ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam put-role-policy --role-name "$EXEC_ROLE" --policy-name "${APP}-secrets" --policy-document "{
  \"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",
  \"Resource\":\"arn:aws:secretsmanager:${REGION}:${ACCOUNT_ID}:secret:${APP}/*\"}]}"

ensure_role "$TASK_ROLE" ecs-tasks.amazonaws.com
aws iam put-role-policy --role-name "$TASK_ROLE" --policy-name "${APP}-runtime" --policy-document "{
  \"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"dynamodb:PutItem\",\"dynamodb:Scan\"],
  \"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/${TABLE}\"}]}"

ensure_role "$INFRA_ROLE" ecs.amazonaws.com
aws iam attach-role-policy --role-name "$INFRA_ROLE" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
echo "Waiting 15s for IAM roles to propagate..."; sleep 15

APPKEY_ARN="$(aws secretsmanager describe-secret --secret-id "${APP}/app-api-key" --region "$REGION" --query ARN --output text)"
SECRETS="{\"name\":\"APP_API_KEY\",\"valueFrom\":\"${APPKEY_ARN}\"}"
if aws secretsmanager describe-secret --secret-id "${APP}/anthropic-api-key" --region "$REGION" >/dev/null 2>&1; then
  ANT_ARN="$(aws secretsmanager describe-secret --secret-id "${APP}/anthropic-api-key" --region "$REGION" --query ARN --output text)"
  SECRETS="${SECRETS},{\"name\":\"ANTHROPIC_API_KEY\",\"valueFrom\":\"${ANT_ARN}\"}"
fi

cat > /tmp/ecs-express.json <<JSON
{
  "serviceName": "${APP}",
  "executionRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${EXEC_ROLE}",
  "taskRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${TASK_ROLE}",
  "infrastructureRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${INFRA_ROLE}",
  "healthCheckPath": "/health",
  "cpu": "256",
  "memory": "512",
  "primaryContainer": {
    "image": "${IMAGE}",
    "containerPort": 8000,
    "environment": [
      {"name": "DDB_TABLE", "value": "${TABLE}"},
      {"name": "APP_REGION", "value": "${REGION}"}
    ],
    "secrets": [ ${SECRETS} ]
  },
  "scalingTarget": {"minTaskCount": 1, "maxTaskCount": 2}
}
JSON

echo "== Creating the ECS Express service (takes a few minutes) =="
SERVICE_ARN="$(aws ecs create-express-gateway-service --cli-input-json file:///tmp/ecs-express.json \
  --region "$REGION" --query service.serviceArn --output text)"
echo "Created: ${SERVICE_ARN}"

echo -n "Waiting for the URL"
URL=""
for _ in $(seq 1 60); do
  URL="$(aws ecs describe-express-gateway-service --service-arn "$SERVICE_ARN" --region "$REGION" \
    --query 'service.activeConfigurations[0].ingressPaths[0].endpoint' --output text 2>/dev/null || true)"
  [ -n "$URL" ] && [ "$URL" != "None" ] && break
  echo -n "."; sleep 10
done
echo
[ -z "$URL" ] || [ "$URL" = "None" ] && { echo "URL not ready yet. Check: ECS console > Clusters > default > ${APP}"; exit 1; }
case "$URL" in http*) ;; *) URL="https://${URL}";; esac

echo -n "Waiting for the app to answer /health"
for _ in $(seq 1 60); do
  curl -fsS "${URL}/health" >/dev/null 2>&1 && break
  echo -n "."; sleep 10
done
echo
echo "Service URL:  ${URL}"
echo "Health check: ${URL}/health"