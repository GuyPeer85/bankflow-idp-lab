import json
import re
import subprocess


KUBERNETES_NAME_PATTERN = re.compile(
    r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
)

FAILED_WAITING_REASONS = {
    "CrashLoopBackOff": (
        "The application starts and repeatedly crashes."
    ),
    "ErrImagePull": (
        "Kubernetes could not pull the container image."
    ),
    "ImagePullBackOff": (
        "Kubernetes is backing off after image pull failures."
    ),
}


class RuntimeLookupError(Exception):
    """Raised when runtime state cannot be read."""


class RuntimeResourceNotFoundError(Exception):
    """Raised when a requested runtime resource does not exist."""


def validate_resource_name(value, field_name):
    if not KUBERNETES_NAME_PATTERN.fullmatch(value):
        raise ValueError(
            f"{field_name} must be a valid lowercase Kubernetes name"
        )


def kubectl_get_json(arguments):
    command = [
        "kubectl",
        "get",
        *arguments,
        "-o",
        "json",
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    if result.returncode != 0:
        error_message = result.stderr.strip()

        if "NotFound" in error_message:
            raise RuntimeResourceNotFoundError(error_message)

        raise RuntimeLookupError(
            error_message or "kubectl could not read runtime state"
        )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeLookupError(
            "kubectl returned invalid JSON"
        ) from error


def find_runtime_problems(pods):
    problems = []

    for pod in pods.get("items", []):
        pod_name = pod.get("metadata", {}).get(
            "name",
            "unknown-pod",
        )

        for condition in pod.get("status", {}).get(
            "conditions",
            [],
        ):
            if (
                condition.get("type") == "PodScheduled"
                and condition.get("status") == "False"
            ):
                problems.append(
                    {
                        "pod": pod_name,
                        "reason": condition.get(
                            "reason",
                            "Unschedulable",
                        ),
                        "message": condition.get(
                            "message",
                            "Kubernetes could not schedule the Pod.",
                        ),
                    }
                )

        for container_status in pod.get("status", {}).get(
            "containerStatuses",
            [],
        ):
            waiting = container_status.get(
                "state",
                {},
            ).get("waiting")

            if not waiting:
                continue

            reason = waiting.get("reason")

            if reason in FAILED_WAITING_REASONS:
                problems.append(
                    {
                        "pod": pod_name,
                        "reason": reason,
                        "message": FAILED_WAITING_REASONS[reason],
                    }
                )

    return problems


def get_service_runtime_status(service_name, environment):
    validate_resource_name(service_name, "service_name")
    validate_resource_name(environment, "environment")

    application_name = f"{service_name}-{environment}"

    application = kubectl_get_json(
        [
            "application",
            application_name,
            "-n",
            "argocd",
        ]
    )

    deployment = kubectl_get_json(
        [
            "deployment",
            service_name,
            "-n",
            environment,
        ]
    )

    pods = kubectl_get_json(
        [
            "pods",
            "-n",
            environment,
            "-l",
            f"app.kubernetes.io/name={service_name}",
        ]
    )

    application_status = application.get("status", {})
    deployment_spec = deployment.get("spec", {})
    deployment_status = deployment.get("status", {})

    sync_status = application_status.get(
        "sync",
        {},
    ).get("status", "Unknown")

    health_status = application_status.get(
        "health",
        {},
    ).get("status", "Unknown")

    desired_replicas = deployment_spec.get("replicas", 0)
    ready_replicas = deployment_status.get("readyReplicas", 0)
    available_replicas = deployment_status.get(
        "availableReplicas",
        0,
    )

    problems = find_runtime_problems(pods)

    if problems or health_status in {"Degraded", "Missing"}:
        status = "failed"
        summary = "The service requires attention."
    elif (
        sync_status == "Synced"
        and health_status == "Healthy"
        and ready_replicas >= desired_replicas
    ):
        status = "healthy"
        summary = "The service is synced and ready."
    else:
        status = "progressing"
        summary = "The platform is still reconciling the service."

    return {
        "serviceName": service_name,
        "environment": environment,
        "status": status,
        "summary": summary,
        "argocd": {
            "application": application_name,
            "syncStatus": sync_status,
            "healthStatus": health_status,
        },
        "kubernetes": {
            "deployment": service_name,
            "desiredReplicas": desired_replicas,
            "readyReplicas": ready_replicas,
            "availableReplicas": available_replicas,
        },
        "problems": problems,
    }
def get_all_service_runtime_statuses():
    applications = kubectl_get_json(
        [
            "applications",
            "-n",
            "argocd",
            "-l",
            "bankflow.io/managed-by=applicationset",
        ]
    )

    services = []

    for application in applications.get("items", []):
        labels = application.get(
            "metadata",
            {},
        ).get(
            "labels",
            {},
        )

        service_name = labels.get(
            "bankflow.io/service"
        )

        environment = labels.get(
            "bankflow.io/environment"
        )

        if not service_name or not environment:
            continue

        try:
            status = get_service_runtime_status(
                service_name=service_name,
                environment=environment,
            )

        except RuntimeResourceNotFoundError:
            status = {
                "serviceName": service_name,
                "environment": environment,
                "status": "not-found",
                "summary": (
                    "Runtime resources were not found."
                ),
                "problems": [],
            }

        except RuntimeLookupError as error:
            status = {
                "serviceName": service_name,
                "environment": environment,
                "status": "unavailable",
                "summary": (
                    "Runtime status could not be read."
                ),
                "problems": [str(error)],
            }

        services.append(status)

    services.sort(
        key=lambda item: (
            item["serviceName"],
            item["environment"],
        )
    )

    return {
        "count": len(services),
        "services": services,
    }