#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_ROOT}"

if [[ $# -ne 2 ]]; then
  echo "Usage:"
  echo "  $0 <request-file> <output-file>"
  exit 64
fi

REQUEST_FILE="$1"
OUTPUT_FILE="$2"

PROFILES_FILE="platform/catalog/resource-profiles.json"
VALIDATOR="platform/worker/validate_request.py"
CHART_DIR="platform/golden-paths/http-api"

if [[ ! -f "${REQUEST_FILE}" ]]; then
  echo "[REJECTED] Request file does not exist: ${REQUEST_FILE}"
  exit 1
fi

readarray -t REQUEST_DATA < <(
  python3 - "${REQUEST_FILE}" <<'PYTHON'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    request = json.load(file)

print(request["metadata"]["name"])
print(request["spec"]["environment"])
print(request["spec"]["workloadType"])
print(request["spec"]["goldenPath"]["version"])
PYTHON
)

SERVICE_NAME="${REQUEST_DATA[0]}"
ENVIRONMENT="${REQUEST_DATA[1]}"
WORKLOAD_TYPE="${REQUEST_DATA[2]}"
REQUESTED_GOLDEN_PATH_VERSION="${REQUEST_DATA[3]}"

if [[ "${WORKLOAD_TYPE}" != "http-api" ]]; then
  echo "[REJECTED] This worker supports only workloadType=http-api"
  exit 1
fi

CHART_VERSION="$(
  helm show chart "${CHART_DIR}" |
    awk '$1 == "version:" { print $2 }'
)"

if [[ "${CHART_VERSION}" != "${REQUESTED_GOLDEN_PATH_VERSION}" ]]; then
  echo "[REJECTED] Golden Path version mismatch"
  echo "  Request version: ${REQUESTED_GOLDEN_PATH_VERSION}"
  echo "  Chart version:   ${CHART_VERSION}"
  exit 1
fi

echo "[1/4] Validating ServiceRequest"

python3 "${VALIDATOR}" \
  --profiles "${PROFILES_FILE}" \
  "${REQUEST_FILE}"

echo "[2/4] Validating Golden Path"

helm lint "${CHART_DIR}" \
  -f "${PROFILES_FILE}" \
  -f "${REQUEST_FILE}"

TEMP_FILE="$(mktemp)"
trap 'rm -f "${TEMP_FILE}"' EXIT

echo "[3/4] Rendering Kubernetes manifests"

helm template "${SERVICE_NAME}" \
  "${CHART_DIR}" \
  --namespace "${ENVIRONMENT}" \
  -f "${PROFILES_FILE}" \
  -f "${REQUEST_FILE}" \
  > "${TEMP_FILE}"

echo "[4/4] Asking Kubernetes API to validate the result"

kubectl apply \
  --dry-run=server \
  -f "${TEMP_FILE}" \
  >/dev/null

mkdir -p "$(dirname -- "${OUTPUT_FILE}")"

if [[ -f "${OUTPUT_FILE}" ]] && cmp -s "${TEMP_FILE}" "${OUTPUT_FILE}"; then
  echo "[NO CHANGE] Generated manifest is already up to date"
else
  cp -- "${TEMP_FILE}" "${OUTPUT_FILE}"
  echo "[RENDERED] ${OUTPUT_FILE}"
fi

echo
echo "Service:             ${SERVICE_NAME}"
echo "Environment:         ${ENVIRONMENT}"
echo "Workload type:       ${WORKLOAD_TYPE}"
echo "Golden Path version: ${CHART_VERSION}"
echo "[SUCCESS] Request validated and rendered"