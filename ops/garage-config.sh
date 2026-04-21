#!/usr/bin/env bash

# Configures a local Garage installation to use it as an S3 backend.
#
# Flow:
# 1. Assigns the node to the layout with a zone and capacity.
# 2. Shows the current layout and applies it.
# 3. Creates the bucket where Pulumi will store its state.
# 4. Creates an access key and grants it permissions on the bucket.
# 5. Verifies S3 access using AWS CLI against the local endpoint.
#
# Environment-configurable variables:
#   CLUSTER_ID
#   GARAGE_ZONE
#   GARAGE_CAPACITY
#   LAYOUT_VERSION
#   PULUMI_BUCKET_NAME
#   PULUMI_KEY_NAME
#   GARAGE_CONTAINER
#   GARAGE_BINARY
#   AWS_ENDPOINT_URL
#
# Example:
#   CLUSTER_ID=24c7fd98c928d5d4 infra/initial_provision/garage-config.sh
#
# Important:
#   You must set CLUSTER_ID to the node identifier of your Garage instance.
#   You can obtain it with:
#     make garage status

set -euo pipefail

CLUSTER_ID="${CLUSTER_ID:-6c71cd6262902823}"
GARAGE_ZONE="${GARAGE_ZONE:-dc1}"
GARAGE_CAPACITY="${GARAGE_CAPACITY:-128MB}"
LAYOUT_VERSION="${LAYOUT_VERSION:-1}"
PULUMI_BUCKET_NAME="${PULUMI_BUCKET_NAME:-pulumi-infra}"
PULUMI_KEY_NAME="${PULUMI_KEY_NAME:-pulumi-bucket-key}"
GARAGE_CONTAINER="${GARAGE_CONTAINER:-garage}"
GARAGE_BINARY="${GARAGE_BINARY:-/garage}"
AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://127.0.0.1:33900}"

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Error: required command '${command_name}' is missing." >&2
    exit 1
  fi
}

garage() {
  docker compose exec -T "${GARAGE_CONTAINER}" "${GARAGE_BINARY}" "$@"
}

step() {
  echo
  echo "==> $*"
}

main() {
  require_command docker
  require_command aws

  step "Assigning node ${CLUSTER_ID} to the layout"
  garage layout assign -z "${GARAGE_ZONE}" -c "${GARAGE_CAPACITY}" "${CLUSTER_ID}"

  step "Showing current layout"
  garage layout show

  step "Applying layout version ${LAYOUT_VERSION}"
  garage layout apply --version "${LAYOUT_VERSION}"

  step "Creating bucket ${PULUMI_BUCKET_NAME}"
  garage bucket create "${PULUMI_BUCKET_NAME}"

  step "Inspecting bucket ${PULUMI_BUCKET_NAME}"
  garage bucket list
  garage bucket info "${PULUMI_BUCKET_NAME}"

  step "Creating key ${PULUMI_KEY_NAME}"
  garage key create "${PULUMI_KEY_NAME}"

  step "Granting read and write access to the bucket"
  garage bucket allow \
    --read \
    --write \
    "${PULUMI_BUCKET_NAME}" \
    --key "${PULUMI_KEY_NAME}"

  step "Verifying S3 access against ${AWS_ENDPOINT_URL}"
  aws --endpoint-url "${AWS_ENDPOINT_URL}" s3 ls "s3://${PULUMI_BUCKET_NAME}/"
}

main "$@"
