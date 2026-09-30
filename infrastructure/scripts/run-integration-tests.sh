#!/usr/bin/env bash
set -euo pipefail

environment="${1:?Usage: run-integration-tests.sh dev|prod}"
case "$environment" in
  dev|prod) ;;
  *) echo "Environment must be dev or prod" >&2; exit 1 ;;
esac

cd "$(dirname "$0")/../.."
outputs=$(terraform -chdir="infrastructure/${environment}" output -json)
tf_output() {
  jq -er --arg name "$1" '.[$name].value' <<< "$outputs"
}

export ENVIRONMENT="$environment"
export AWS_PROFILE_NAME="${AWS_PROFILE_NAME:-}"
export RUN_INTEGRATION_TESTS=1
export AWS_REGION="${AWS_REGION:?AWS_REGION is required}"
table=$(tf_output dynamodb_table_names | jq -er '.sites')
prefix="${table%_sites}"
export PROJECT_NAME="${prefix#${environment}_}"
APPLICATION_S3_BUCKET=$(tf_output application_s3_bucket_name)
CRAWL_QUEUE_URL=$(tf_output sqs_queue_urls | jq -er '.crawl')
COGNITO_USER_POOL_ID=$(tf_output cognito_user_pool_id)
COGNITO_APP_CLIENT_ID=$(tf_output cognito_web_client_id)
export APPLICATION_S3_BUCKET CRAWL_QUEUE_URL COGNITO_USER_POOL_ID COGNITO_APP_CLIENT_ID
export CORS_ORIGINS="http://localhost"

if [[ "$environment" == prod ]]; then
  INTEGRATION_API_URL=$(tf_output application_url)
  export INTEGRATION_API_URL
  aws ecs wait services-stable \
    --cluster "$(tf_output backend_ecs_cluster_name)" \
    --services "$(tf_output backend_ecs_service_name)"
else
  : "${GUEST_EMAIL:?Set the dev environment GUEST_EMAIL secret}"
  : "${GUEST_PASSWORD:?Set the dev environment GUEST_PASSWORD secret}"
fi

cd backend
python -m pytest tests/integrated -v -s --tb=short --junitxml=integration-results.xml
