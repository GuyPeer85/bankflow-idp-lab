#!/usr/bin/env python3

import importlib.util
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from apps.api.models import ServiceRequest
from apps.api.runtime_status import (
    RuntimeLookupError,
    RuntimeResourceNotFoundError,
    get_all_service_runtime_statuses,
    get_service_runtime_status,
)
from apps.api.service_creator import (
    ServiceAlreadyExistsError,
    WorkerExecutionError,
    create_service_draft,
)


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

PORTAL_ROOT = (
    REPOSITORY_ROOT
    / "apps"
    / "portal"
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

def validate_against_platform(
    service_request: ServiceRequest,
):
    """
    ממיר את מודל Pydantic לנתונים רגילים
    ומפעיל את מדיניות הפלטפורמה.
    """

    request_data = service_request.model_dump(
        by_alias=True,
        exclude_none=True,
    )

    profiles = validator.load_json(
        PROFILES_PATH
    )

    errors = validator.validate_request(
        request_data,
        profiles,
    )

    return request_data, errors

app = FastAPI(
    title="Bankflow Platform API",
    description=(
        "API for validating and processing internal "
        "developer platform service requests"
    ),
    version="0.1.0",
)

app.mount(
    "/static",
    StaticFiles(directory=PORTAL_ROOT),
    name="static",
)

@app.get("/", include_in_schema=False)
def developer_portal():
    """
    מחזיר את עמוד הבית של פורטל המפתחים.
    """

    return FileResponse(
        PORTAL_ROOT / "index.html"
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


@app.get(
    "/api/v1/services/status"
)
def all_service_runtime_statuses():
    """Returns runtime status for every managed service."""

    try:
        return get_all_service_runtime_statuses()
    except RuntimeLookupError as error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "summary": "Service catalog could not be read.",
                "errors": [str(error)],
            },
        )


@app.get(
    "/api/v1/services/{environment}/{service_name}/status"
)
def service_runtime_status(
    environment: str,
    service_name: str,
):
    """Returns a developer-friendly runtime summary."""

    try:
        return get_service_runtime_status(
            service_name=service_name,
            environment=environment,
        )
    except ValueError as error:
        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "errors": [str(error)],
            },
        )
    except RuntimeResourceNotFoundError:
        return JSONResponse(
            status_code=404,
            content={
                "status": "not-found",
                "summary": (
                    "The service is not deployed in this environment."
                ),
            },
        )
    except RuntimeLookupError as error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "summary": (
                    "Runtime status could not be read."
                ),
                "errors": [str(error)],
            },
        )


@app.post("/api/v1/service-requests/validate")

def validate_service_request(
    service_request: ServiceRequest,
):
    """
    מקבל ServiceRequest, בודק אותו ומחזיר:
    - Approved עם תצוגה מקדימה.
    - Rejected עם רשימת שגיאות.
    """
    request_data, errors = (
        validate_against_platform(
            service_request
        )
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

@app.post(
    "/api/v1/service-requests",
    status_code=201,
)
def create_service_request(
    service_request: ServiceRequest,
):
    """
    מאמת בקשת שירות ויוצר טיוטת GitOps מקומית.

    הפעולה אינה מבצעת commit, push או deployment.
    """

    request_data, errors = (
        validate_against_platform(
            service_request
        )
    )

    if errors:
        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "created": False,
                "errors": errors,
            },
        )

    try:
        draft = create_service_draft(
            request_data=request_data,
            repository_root=REPOSITORY_ROOT,
        )

    except ServiceAlreadyExistsError as error:
        return JSONResponse(
            status_code=409,
            content={
                "status": "conflict",
                "created": False,
                "errors": [
                    str(error),
                ],
            },
        )

    except WorkerExecutionError as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "worker-failed",
                "created": False,
                "errors": [
                    str(error),
                ],
            },
        )

    return {
        "status": "draft-created",
        "created": True,
        "draft": draft,
    }
