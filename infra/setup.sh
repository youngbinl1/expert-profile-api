#!/usr/bin/env bash
# Creates the AWS resources for expert-profile-api. Run it in AWS CloudShell (or any shell with the AWS CLI).
#
#   export GITHUB_REPO="your-github-user/expert-profile-api"
#   export ANTHROPIC_API_KEY="sk-ant-..."     # optional - without it the service runs in template mode
#   bash infra/setup.sh
#
# Safe to re-run: every step checks whether the resource already exists.
set -euo pipefail

REGION="${APP_REGION:-ap-northeast-2}"
APP="expert-profile-api"
TABLE="${APP}-history"
: "${GITHUB_REPO:?Set GITHUB_REPO first, e.g. export GITHUB_REPO=your-user/expert-profile-api}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
echo "Account: ${ACCOUNT_ID}   Region: ${REGION}"

echo "== 1/6 DynamoDB table (history, auto-expiring) =="
if ! aws dynamodb describe-table --table-name "$TABLE" --region "$REGION" >/dev/null 2>&1; then
  aws dynamodb create-table --table-name "$TABLE" \
    --attribute-definitions AttributeName=id,AttributeType=S \
    --key-schema AttributeName=id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST --region "$REGION" >/dev/null
  aws dynamodb wait table-exists --table-name "$TABLE" --region "$REGION"
  aws dynamodb update-time-to-live --table-name "$TABLE" --region "$REGION" \
    --time-to-live-specification "Enabled=true,AttributeName=expires_at" >/dev/null
fi

echo "== 2/6 ECR repository =="
aws ecr describe-repositories --repository-names "$APP" --region "$REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "$APP" --region "$REGION" \
    --image-scanning-configuration scanOnPush=true >/dev/null

echo "== 3/6 Secrets Manager =="
put_secret() {  # name value -> prints ARN
  if aws secretsmanager describe-secret --secret-id "$1" --region "$REGION" >/dev/null 2>&1; then
    aws secretsmanager put-secret-value --secret-id "$1" --secret-string "$2" --region "$REGION" >/dev/null
  else
    aws secretsmanager create-secret --name "$1" --secret-string "$2" --region "$REGION" >/dev/null
  fi
  aws secretsmanager describe-secret --secret-id "$1" --region "$REGION" --query ARN --output text
}
if aws secretsmanager describe-secret --secret-id "${APP}/app-api-key" --region "$REGION" >/dev/null 2>&1; then
  APP_API_KEY="$(aws secretsmanager get-secret-value --secret-id "${APP}/app-api-key" --region "$REGION" --query SecretString --output text)"
else
  APP_API_KEY="$(openssl rand -hex 24)"
fi
put_secret "${APP}/app-api-key" "$APP_API_KEY" >/dev/null
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  put_secret "${APP}/anthropic-api-key" "$ANTHROPIC_API_KEY" >/dev/null
fi

echo "== 4/6 IAM role for App Runner to pull images from ECR =="
ACCESS_ROLE="${APP}-apprunner-ecr-access"
if ! aws iam get-role --role-name "$ACCESS_ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ACCESS_ROLE" --assume-role-policy-document '{
    "Version":"2012-10-17","Statement":[{"Effect":"Allow",
    "Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ACCESS_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
fi

echo "== 5/6 IAM role for the running service (least privilege) =="
INSTANCE_ROLE="${APP}-apprunner-instance"
if ! aws iam get-role --role-name "$INSTANCE_ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$INSTANCE_ROLE" --assume-role-policy-document '{
    "Version":"2012-10-17","Statement":[{"Effect":"Allow",
    "Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
fi
aws iam put-role-policy --role-name "$INSTANCE_ROLE" --policy-name "${APP}-runtime" --policy-document "{
  \"Version\":\"2012-10-17\",\"Statement\":[
    {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:PutItem\",\"dynamodb:Scan\"],
     \"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/${TABLE}\"},
    {\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",
     \"Resource\":\"arn:aws:secretsmanager:${REGION}:${ACCOUNT_ID}:secret:${APP}/*\"}]}"

echo "== 6/6 GitHub Actions deploy role (OIDC, no stored AWS keys) =="
OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
if ! aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN" >/dev/null 2>&1; then
  aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 1c58a3a8518e8759bf075b76b750d4f2df264fcd >/dev/null
fi
DEPLOY_ROLE="${APP}-github-deploy"
TRUST="{
  \"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",
  \"Principal\":{\"Federated\":\"${OIDC_ARN}\"},\"Action\":\"sts:AssumeRoleWithWebIdentity\",
  \"Condition\":{\"StringEquals\":{\"token.actions.githubusercontent.com:aud\":\"sts.amazonaws.com\"},
  \"StringLike\":{\"token.actions.githubusercontent.com:sub\":\"repo:${GITHUB_REPO}:ref:refs/heads/main\"}}}]}"
if aws iam get-role --role-name "$DEPLOY_ROLE" >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name "$DEPLOY_ROLE" --policy-document "$TRUST"
else
  aws iam create-role --role-name "$DEPLOY_ROLE" --assume-role-policy-document "$TRUST" >/dev/null
fi
aws iam put-role-policy --role-name "$DEPLOY_ROLE" --policy-name "${APP}-ecr-push" --policy-document "{
  \"Version\":\"2012-10-17\",\"Statement\":[
    {\"Effect\":\"Allow\",\"Action\":\"ecr:GetAuthorizationToken\",\"Resource\":\"*\"},
    {\"Effect\":\"Allow\",\"Action\":[\"ecr:BatchCheckLayerAvailability\",\"ecr:InitiateLayerUpload\",
      \"ecr:UploadLayerPart\",\"ecr:CompleteLayerUpload\",\"ecr:PutImage\",\"ecr:BatchGetImage\"],
     \"Resource\":\"arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/${APP}\"}]}"

echo
echo "=============================================================="
echo " Done. Next:"
echo "  1) In GitHub: Settings > Secrets and variables > Actions > Variables, add"
echo "       AWS_REGION   = ${REGION}"
echo "       AWS_ROLE_ARN = arn:aws:iam::${ACCOUNT_ID}:role/${DEPLOY_ROLE}"
echo "  2) Push the code to the 'main' branch so Actions builds the first image."
echo "  3) Then run:  bash infra/create-service.sh"
echo
echo " Your API key for the web UI (also stored in Secrets Manager):"
echo "   ${APP_API_KEY}"
echo "=============================================================="
