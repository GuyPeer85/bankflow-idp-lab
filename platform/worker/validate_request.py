#!/usr/bin/env python3

import argparse
import copy
import json
import re
import sys
from datetime import date
from pathlib import Path


DNS_NAME_PATTERN = re.compile(
    r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
)

ALLOWED_ENVIRONMENTS = {"dev", "test", "prod"}
ALLOWED_WORKLOAD_TYPES = {"http-api", "frontend", "background-worker"}
ALLOWED_EXPOSURES = {"internal", "external"}
ALLOWED_APPROVERS = {"platform-team", "security-team"}


def load_json(path):
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def require(errors, condition, message):
    if not condition:
        errors.append(message)


def validate_request(request, profiles):
    errors = []

    metadata = request.get("metadata", {})
    spec = request.get("spec", {})
    golden_path = spec.get("goldenPath", {})
    image = spec.get("image", {})
    features = spec.get("features", {})

    name = metadata.get("name")
    owner = metadata.get("owner")
    environment = spec.get("environment")
    workload_type = spec.get("workloadType")
    exposure = spec.get("exposure")
    cluster_class = spec.get("clusterClass")
    size = spec.get("size")
    replicas = spec.get("replicas")
    image_repository = image.get("repository")
    image_tag = image.get("tag")
    channel = golden_path.get("channel")
    golden_path_version = golden_path.get("version")
    pilot_mode = features.get("pilotMode", False)
    autoscaling = features.get("autoscaling", False)

    pod_disruption_budget = features.get(
        "podDisruptionBudget",
        False,
    )

    require(
        errors,
        request.get("apiVersion") == "platform.bankflow.io/v1alpha1",
        "apiVersion must be platform.bankflow.io/v1alpha1",
    )

    require(
        errors,
        request.get("kind") == "ServiceRequest",
        "kind must be ServiceRequest",
    )

    require(
        errors,
        isinstance(name, str) and bool(DNS_NAME_PATTERN.fullmatch(name)),
        "metadata.name must be a valid lowercase Kubernetes name",
    )

    require(
        errors,
        isinstance(owner, str) and bool(owner.strip()),
        "metadata.owner is required",
    )

    require(
        errors,
        environment in ALLOWED_ENVIRONMENTS,
        f"environment must be one of: {sorted(ALLOWED_ENVIRONMENTS)}",
    )

    require(
        errors,
        workload_type in ALLOWED_WORKLOAD_TYPES,
        f"workloadType must be one of: {sorted(ALLOWED_WORKLOAD_TYPES)}",
    )

    require(
        errors,
        exposure in ALLOWED_EXPOSURES,
        f"exposure must be one of: {sorted(ALLOWED_EXPOSURES)}",
    )

    require(
        errors,
        cluster_class == "general",
        "clusterClass must currently be general",
    )

    require(
        errors,
        size in profiles,
        f"size must exist in the resource catalog: {sorted(profiles)}",
    )

    require(
        errors,
        type(replicas) is int and replicas >= 1,
        "replicas must be a whole number greater than zero",
    )

    if size in profiles and type(replicas) is int:
        maximum = profiles[size]["replicas"]["maximum"]

        require(
            errors,
            replicas <= maximum,
            f"replicas={replicas} exceeds the maximum of {maximum} "
            f"for size={size}",
        )

    require(
    errors,
    type(autoscaling) is bool,
    "features.autoscaling must be true or false",
)

    require(
        errors,
        type(pod_disruption_budget) is bool,
        "features.podDisruptionBudget must be true or false",
    )

    if autoscaling and size in profiles and type(replicas) is int:
        maximum = profiles[size]["replicas"]["maximum"]

        require(
            errors,
            replicas < maximum,
            "autoscaling requires room between replicas "
            f"and the maximum of {maximum} for size={size}",
        )

    if pod_disruption_budget and type(replicas) is int:
        require(
            errors,
            replicas >= 2,
            "podDisruptionBudget requires at least 2 replicas",
        )
    require(
        errors,
        isinstance(image_repository, str) and bool(image_repository.strip()),
        "image.repository is required",
    )

    require(
        errors,
        isinstance(image_tag, str)
        and bool(image_tag.strip())
        and image_tag != "latest",
        "image.tag is required and cannot be latest",
    )

    require(
        errors,
        isinstance(golden_path_version, str)
        and bool(golden_path_version.strip()),
        "goldenPath.version is required",
    )

    is_pilot = channel == "pilot" or pilot_mode is True

    if is_pilot:
        require(
            errors,
            channel == "pilot" and pilot_mode is True,
            "a pilot request must use channel=pilot and pilotMode=true",
        )

        require(
            errors,
            environment != "prod",
            "pilot workloads cannot be deployed directly to prod",
        )

        exception = spec.get("exception", {})

        for field in ("id", "reason", "approvedBy", "expiresAt"):
            require(
                errors,
                isinstance(exception.get(field), str)
                and bool(exception.get(field).strip()),
                f"pilot exception requires exception.{field}",
            )

        approved_by = exception.get("approvedBy")

        if approved_by:
            require(
                errors,
                approved_by in ALLOWED_APPROVERS,
                f"exception.approvedBy must be one of: "
                f"{sorted(ALLOWED_APPROVERS)}",
            )

        expires_at = exception.get("expiresAt")

        if expires_at:
            try:
                expiration_date = date.fromisoformat(expires_at)

                require(
                    errors,
                    expiration_date >= date.today(),
                    "pilot exception has expired",
                )
            except ValueError:
                errors.append(
                    "exception.expiresAt must use YYYY-MM-DD format"
                )

    elif "exception" in spec:
        errors.append(
            "a stable request should not contain a pilot exception"
        )

    return errors


def print_validation_result(path, errors):
    if errors:
        print(f"[REJECTED] {path}")

        for error in errors:
            print(f"  - {error}")

        return False

    print(f"[APPROVED] {path}")
    return True


def run_anomaly_demo(requests, profiles):
    print("\n--- Anomaly tests ---")

    standard = next(
        (
            request
            for request in requests
            if request.get("spec", {})
            .get("features", {})
            .get("pilotMode") is False
        ),
        None,
    )

    pilot = next(
        (
            request
            for request in requests
            if request.get("spec", {})
            .get("features", {})
            .get("pilotMode") is True
        ),
        None,
    )

    if pilot:
        missing_expiry = copy.deepcopy(pilot)
        missing_expiry["spec"]["exception"].pop("expiresAt", None)

        errors = validate_request(missing_expiry, profiles)

        if errors:
            print("[EXPECTED REJECTION] pilot without expiration date")
            for error in errors:
                print(f"  - {error}")
        else:
            print("[TEST FAILED] pilot without expiration was approved")

    if standard:
        excessive_resources = copy.deepcopy(standard)
        excessive_resources["spec"]["replicas"] = 99

        errors = validate_request(excessive_resources, profiles)

        if errors:
            print("[EXPECTED REJECTION] excessive replica request")
            for error in errors:
                print(f"  - {error}")
        else:
            print("[TEST FAILED] excessive replica request was approved")


def main():
    parser = argparse.ArgumentParser(
        description="Validate Bankflow platform service requests"
    )

    parser.add_argument(
        "--profiles",
        required=True,
        help="Path to the resource profiles catalog",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run deliberate anomaly tests",
    )

    parser.add_argument(
        "requests",
        nargs="+",
        help="Service request JSON files",
    )

    args = parser.parse_args()

    profiles = load_json(args.profiles)
    loaded_requests = []
    all_valid = True

    for request_path in args.requests:
        request = load_json(request_path)
        loaded_requests.append(request)

        errors = validate_request(request, profiles)

        if not print_validation_result(request_path, errors):
            all_valid = False

    if args.demo:
        run_anomaly_demo(loaded_requests, profiles)

    if not all_valid:
        sys.exit(1)


if __name__ == "__main__":
    main()