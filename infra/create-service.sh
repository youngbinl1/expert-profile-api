#!/usr/bin/env bash
# Creates the App Runner service. Run AFTER GitHub Actions has pushed the first image to ECR.
#   bash infra/create-service.sh
set -euo pipefail

REGION="${APP_REGION:-ap-northeast-2}"
APP="expert-profile-api"
TABLE="${APP}-history"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
IMAGE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${APP}:latest"

aws ecr describe-images --repository-name "$APP" --image-ids imageTag=latest --region "$REGION" >/dev/null 2>&1 || {
  echo "No ':latest' image in ECR yet. Push to GitHub and wait for the Actions run to finish first."; exit 1; }

APPKEY_ARN="$(aws secretsmanager describe-secret --secret-id "${APP}/app-api-key" --region "$REGION" --query ARN --output text)"
SECRETS="\"APP_API_KEY\": \"${APPKEY_ARN}\""
if aws secretsmanager describe-secret --secret-id "${APP}/anthropic-api-key" --region "$REGION" >/dev/null 2>&1; then
  ANT_ARN="$(aws secretsmanager describe-secret --secret-id "${APP}/anthropic-api-key" --region "$REGION" --query ARN --output text)"
  SECRETS="${SECRETS}, \"ANTHROPIC_API_KEY\": \"${ANT_ARN}\""
fi

cat > /tmp/apprunner-service.json <<JSON
{
  "ServiceName": "${APP}",
  "SourceConfiguration": {
    "AuthenticationConfiguration": {
      "AccessRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${APP}-apprunner-ecr-access"
    },
    "AutoDeploymentsEnabled": true,
    "ImageRepository": {
      "ImageIdentifier": "${IMAGE}",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8000",
        "RuntimeEnvironmentVariables": {
          "DDB_TABLE": "${TABLE}",
          "APP_REGION": "${REGION}"
        },
        "RuntimeEnvironmentSecrets": { ${SECRETS} }
      }
    }
  },
  "InstanceConfiguration": {
    "Cpu": "256",
    "Memory": "512",
    "InstanceRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${APP}-apprunner-instance"
  },
  "HealthCheckConfiguration": {
    "Protocol": "HTTP", "Path": "/health",
    "Interval": 10, "Timeout": 5, "HealthyThreshold": 1, "UnhealthyThreshold": 5
  }
}
JSON

SERVICE_ARN="$(aws apprunner create-service --cli-input-json file:///tmp/apprunner-service.json \
  --region "$REGION" --query Service.ServiceArn --output text)"
echo "Created: ${SERVICE_ARN}"
echo -n "Waiting for the service to become RUNNING"
for _ in $(seq 1 60); do
  STATUS="$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$REGION" --query Service.Status --output text)"
  [ "$STATUS" = "RUNNING" ] && break
  [ "$STATUS" = "CREATE_FAILED" ] && { echo; echo "Creation failed - check the App Runner console > Logs."; exit 1; }
  echo -n "."; sleep 10
done
echo
URL="$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$REGION" --query Service.ServiceUrl --output text)"
echo "Service URL:  https://${URL}"
echo "Health check: https://${URL}/health"
