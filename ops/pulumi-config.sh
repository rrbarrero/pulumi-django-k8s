#!/usr/bin/env bash

set -euo pipefail

export AWS_PROFILE=garage
export AWS_REGION=garage
export AWS_DEFAULT_REGION=garage

pulumi login 's3://pulumi-infra?endpoint=127.0.0.1:33900&disableSSL=true&s3ForcePathStyle=true'

pulumi whoami -v