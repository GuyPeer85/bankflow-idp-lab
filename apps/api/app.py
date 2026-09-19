#!/usr/bin/env python3

import importlib.util
from pathlib import Path
from apps.api.models import ServiceRequest
from fastapi import FastAPI
from fastapi.responses import JSONResponse


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

VALIDATOR_PATH = (
    REPOSITORY_ROOT
    / "platform"
    / "worker"
    / "validate_request.py"
)

PROFILES_PATH = (
    REPOSITORY_ROOT
    / "platform"
    / "catalog"
    / "resource-profiles.json"
)


def load_validator_module():
    """
    טוען את ה-Validator הקיים שלנו.

    אנו משתמשים ב-importlib מפני שהתיקייה שלנו נקראת platform,
    וזהו גם שם של מודול מובנה ב-Python.
    """

    module_spec = importlib.util.spec_from_file_location(
        "bankflow_request_validator",
        VALIDATOR_PATH,
    )

    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(
            f"Could not load validator from {VALIDATOR_PATH}"
        )

    validator_module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(validator_module)

    return validator_module


validator = load_validator_module()

app = FastAPI(
    title="Bankflow Platform API",
    description=(
        "API for validating and processing internal "
        "developer platform service requests"
    ),
    version="0.1.0",
)


@app.get("/health/live")
def liveness():
    """
    האם תהליך ה-API חי?
    """

    return {
        "status": "alive",
        "service": "bankflow-platform-api",
    }


@app.get("/health/ready")
def readiness():
    """
    האם ה-API מוכן לקבל בקשות?

    כאן אנחנו בודקים שקובצי התלות החשובים קיימים.
    """

    missing_files = []

    for required_file in [VALIDATOR_PATH, PROFILES_PATH]:
        if not required_file.is_file():
            missing_files.append(str(required_file))

    if missing_files:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not-ready",
                "missingFiles": missing_files,
            },
        )

    return {
        "status": "ready",
        "service": "bankflow-platform-api",
    }


@app.post("/api/v1/service-requests/validate")

def validate_service_request(
    service_request: ServiceRequest,
):
    """
    מקבל ServiceRequest, בודק אותו ומחזיר:
    - Approved עם תצוגה מקדימה.
    - Rejected עם רשימת שגיאות.
    """
    request_data = service_request.model_dump(
        by_alias=True,
        exclude_none=True,
    )

    profiles = validator.load_json(PROFILES_PATH)

    errors = validator.validate_request(
        request_data,
        profiles,
    )

    if errors:
        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "approved": False,
                "errors": errors,
            },
        )

    metadata = request_data["metadata"]
    spec = request_data["spec"]
    image = spec["image"]
    golden_path = spec["goldenPath"]

    preview = {
        "serviceName": metadata["name"],
        "owner": metadata["owner"],
        "environment": spec["environment"],
        "namespace": spec["environment"],
        "image": (
            f"{image['repository']}:{image['tag']}"
        ),
        "replicas": spec["replicas"],
        "size": spec["size"],
        "exposure": spec["exposure"],
        "goldenPath": {
            "name": golden_path["name"],
            "channel": golden_path["channel"],
            "version": golden_path["version"],
        },
        "resourcesToGenerate": [
            "ServiceAccount",
            "Service",
            "Deployment",
        ],
    }

    return {
        "status": "approved",
        "approved": True,
        "message": (
            "ServiceRequest passed the platform guardrails"
        ),
        "preview": preview,
    }