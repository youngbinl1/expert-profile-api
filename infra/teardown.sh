#!/usr/bin/env bash
# Deletes everything created by setup.sh / create-service.sh so nothing keeps costing money.
# (The load balancer behind the service is the main cost, so run this after your demo.)
set -uo pipefail
REGION="${APP_REGION:-ap-northeast-1}"
APP="expert-profile-api"
TABLE="${APP}-history"

ARN="$(aws ecs list-services --region "$REGION" --query "serviceArns[?ends_with(@, '/${APP}')] | [0]" --output text 2>/dev/null)"
if [ -n "$ARN" ] && [ "$ARN" != "None" ]; then
  aws ecs delete-express-gateway-service --service-arn "$ARN" --region "$REGION" >/dev/null && echo "ECS Express service deletion started (takes a few minutes)"
fi
# legacy: App Runner service from the earlier version of this project (only exists on older accounts)
AR="$(aws apprunner list-services --region "$REGION" --query "ServiceSummaryList[?ServiceName=='${APP}'].ServiceArn | [0]" --output text 2>/dev/null)"
if [ -n "$AR" ] && [ "$AR" != "None" ]; then aws apprunner delete-service --service-arn "$AR" --region "$REGION" >/dev/null && echo "App Runner service deletion started"; fi

aws ecr delete-repository --repository-name "$APP" --force --region "$REGION" >/dev/null 2>&1 && echo "ECR repository deleted"
aws dynamodb delete-table --table-name "$TABLE" --region "$REGION" >/dev/null 2>&1 && echo "DynamoDB table deleted"
for s in app-api-key anthropic-api-key; do
  aws secretsmanager delete-secret --secret-id "${APP}/${s}" --force-delete-without-recovery --region "$REGION" >/dev/null 2>&1 && echo "Secret ${s} deleted"
done
for r in "${APP}-ecs-execution" "${APP}-ecs-task" "${APP}-ecs-infrastructure" "${APP}-apprunner-ecr-access" "${APP}-apprunner-instance" "${APP}-github-deploy"; do
  for p in $(aws iam list-attached-role-policies --role-name "$r" --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null); do
    aws iam detach-role-policy --role-name "$r" --policy-arn "$p"
  done
  for p in $(aws iam list-role-policies --role-name "$r" --query 'PolicyNames[]' --output text 2>/dev/null); do
    aws iam delete-role-policy --role-name "$r" --policy-name "$p"
  done
  aws iam delete-role --role-name "$r" >/dev/null 2>&1 && echo "Role ${r} deleted"
done
echo "Done. Wait a few minutes for the ECS service/load balancer to finish deleting, then check the ECS and EC2 consoles are empty."
echo "(The shared GitHub OIDC provider in IAM was left in place; it costs nothing.)"