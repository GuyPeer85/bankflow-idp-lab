import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SAFE_SERVICE_NAME = re.compile(
    r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
)

ALLOWED_ENVIRONMENTS = {
    "dev",
    "test",
    "prod",
}


class ServiceAlreadyExistsError(Exception):
    """
    השירות כבר קיים ולכן אסור לדרוס אותו.
    """


class WorkerExecutionError(Exception):
    """
    ה-Worker נכשל בזמן יצירת ה-Manifests.
    """


def create_service_draft(
    request_data: dict[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    """
    יוצר טיוטת GitOps מקומית מבקשת שירות מאושרת.

    הפונקציה אינה מבצעת Git commit, push או kubectl apply.
    """

    service_name = request_data["metadata"]["name"]
    environment = request_data["spec"]["environment"]

    if not SAFE_SERVICE_NAME.fullmatch(service_name):
        raise ValueError(
            "Unsafe service name"
        )

    if environment not in ALLOWED_ENVIRONMENTS:
        raise ValueError(
            "Unsupported environment"
        )

    request_relative_path = (
        Path("platform")
        / "requests"
        / "services"
        / service_name
        / environment
        / "config.json"
    )

    manifest_relative_path = (
        Path("gitops")
        / "services"
        / service_name
        / environment
        / "workload.yaml"
    )

    request_path = (
        repository_root
        / request_relative_path
    )

    manifest_path = (
        repository_root
        / manifest_relative_path
    )

    if request_path.exists() or manifest_path.exists():
        raise ServiceAlreadyExistsError(
            f"Service {service_name} already exists "
            f"in environment {environment}"
        )

    render_worker = (
        repository_root
        / "platform"
        / "worker"
        / "render_service.sh"
    )

    if not render_worker.is_file():
        raise WorkerExecutionError(
            f"Render worker was not found: {render_worker}"
        )

    with tempfile.TemporaryDirectory(
        prefix="bankflow-service-"
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)

        temporary_request = (
            temporary_root / "config.json"
        )

        temporary_manifest = (
            temporary_root / "workload.yaml"
        )

        temporary_request.write_text(
            json.dumps(
                request_data,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        try:
            worker_result = subprocess.run(
                [
                    str(render_worker),
                    str(temporary_request),
                    str(temporary_manifest),
                ],
                cwd=repository_root,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise WorkerExecutionError(
                "Render worker timed out"
            ) from error

        worker_output = "\n".join(
            part.strip()
            for part in [
                worker_result.stdout,
                worker_result.stderr,
            ]
            if part.strip()
        )

        if worker_result.returncode != 0:
            raise WorkerExecutionError(
                worker_output
                or "Render worker failed"
            )

        if not temporary_manifest.is_file():
            raise WorkerExecutionError(
                "Worker finished without generating a manifest"
            )

        request_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        created_files = []

        try:
            with request_path.open(
                "x",
                encoding="utf-8",
            ) as request_file:
                json.dump(
                    request_data,
                    request_file,
                    indent=2,
                    ensure_ascii=False,
                )

                request_file.write("\n")

            created_files.append(request_path)

            with manifest_path.open("xb") as manifest_file:
                manifest_file.write(
                    temporary_manifest.read_bytes()
                )

            created_files.append(manifest_path)

        except FileExistsError as error:
            for created_file in created_files:
                created_file.unlink(missing_ok=True)

            raise ServiceAlreadyExistsError(
                f"Service {service_name} was created "
                "by another request"
            ) from error

        except Exception:
            for created_file in created_files:
                created_file.unlink(missing_ok=True)

            raise

    return {
        "serviceName": service_name,
        "environment": environment,
        "requestFile": str(request_relative_path),
        "manifestFile": str(manifest_relative_path),
        "workerOutput": worker_output,
        "nextAction": (
            "Review the generated Git changes "
            "and create a pull request"
        ),
    }