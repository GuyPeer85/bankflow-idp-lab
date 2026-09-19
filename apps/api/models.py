from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlatformModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


class ServiceMetadata(PlatformModel):
    name: str
    owner: str


class GoldenPath(PlatformModel):
    name: str
    channel: Literal["stable", "pilot"]
    version: str


class ContainerImage(PlatformModel):
    repository: str
    tag: str


class ServiceFeatures(PlatformModel):
    pilot_mode: bool = Field(
        default=False,
        alias="pilotMode",
    )


class ServiceException(PlatformModel):
    id: str
    reason: str
    approved_by: str = Field(alias="approvedBy")
    expires_at: str = Field(alias="expiresAt")


class ServiceSpec(PlatformModel):
    workload_type: Literal[
        "http-api",
        "frontend",
        "background-worker",
    ] = Field(alias="workloadType")

    environment: Literal["dev", "test", "prod"]

    cluster_class: str = Field(alias="clusterClass")

    golden_path: GoldenPath = Field(alias="goldenPath")

    image: ContainerImage

    size: str

    replicas: int = Field(ge=1)

    exposure: Literal["internal", "external"]

    features: ServiceFeatures

    exception: ServiceException | None = None


class ServiceRequest(PlatformModel):
    api_version: Literal[
        "platform.bankflow.io/v1alpha1"
    ] = Field(alias="apiVersion")

    kind: Literal["ServiceRequest"]

    metadata: ServiceMetadata

    spec: ServiceSpec

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "apiVersion": "platform.bankflow.io/v1alpha1",
                "kind": "ServiceRequest",
                "metadata": {
                    "name": "payments-api",
                    "owner": "payments-team",
                },
                "spec": {
                    "workloadType": "http-api",
                    "environment": "dev",
                    "clusterClass": "general",
                    "goldenPath": {
                        "name": "http-api",
                        "channel": "stable",
                        "version": "1.0.0",
                    },
                    "image": {
                        "repository": "bankflow/payments-api",
                        "tag": "1.0.0",
                    },
                    "size": "small",
                    "replicas": 2,
                    "exposure": "internal",
                    "features": {
                        "pilotMode": False,
                    },
                },
            }
        },
    )