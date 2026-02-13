"""Pydantic schema for the HLD Intermediate Representation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ElementType(str, Enum):
    """Supported architecture element types."""

    CONTAINER = "container"
    DATABASE = "database"
    QUEUE = "queue"
    CACHE = "cache"
    COMPONENT = "component"


class ScalingType(str, Enum):
    """Supported scaling modes."""

    AUTO = "auto"
    MANUAL = "manual"
    NONE = "none"


class Metadata(BaseModel):
    """Document metadata."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str | None = None
    author: str | None = None
    date: str | None = None
    tags: list[str] = Field(default_factory=list)


class SystemInfo(BaseModel):
    """Top-level system definition."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str


class DeploymentInfo(BaseModel):
    """Deployment configuration."""

    model_config = ConfigDict(extra="forbid")

    platform: str | None = None
    scaling: ScalingType | None = None
    replicas: int | None = None


class Component(BaseModel):
    """Component within a container."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    technology: str
    description: str
    type: ElementType = ElementType.COMPONENT
    tags: list[str] = Field(default_factory=list)


class Container(BaseModel):
    """Container or infrastructure element."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    technology: str
    description: str
    type: ElementType
    deployment: DeploymentInfo | None = None
    tags: list[str] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)


class Relationship(BaseModel):
    """Relationship between elements."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    description: str
    protocol: str | None = None
    patterns: list[str] = Field(default_factory=list)
    sync: bool | None = None


class ExternalSystem(BaseModel):
    """External dependency."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    technology: str | None = None
    description: str | None = None
    type: ElementType = ElementType.CONTAINER
    tags: list[str] = Field(default_factory=list)


class Integration(BaseModel):
    """Integration between internal and external systems."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    protocol: str | None = None
    description: str | None = None


class DeploymentEnvironment(BaseModel):
    """Deployment environment metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str
    regions: list[str] = Field(default_factory=list)


class QualityAttribute(BaseModel):
    """Non-functional requirement entry."""

    model_config = ConfigDict(extra="forbid")

    attribute: str
    target: str
    measurement: str


class Decision(BaseModel):
    """Architecture decision record snippet."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    status: str | None = None
    rationale: str | None = None


class IRModel(BaseModel):
    """Root IR model."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: str
    metadata: Metadata
    system: SystemInfo
    containers: list[Container]
    relationships: list[Relationship]
    external_systems: list[ExternalSystem] = Field(
        default_factory=list,
        alias="external-systems",
    )
    integrations: list[Integration] = Field(default_factory=list)
    deployment_environments: list[DeploymentEnvironment] = Field(
        default_factory=list,
        alias="deployment-environments",
    )
    quality_attributes: list[QualityAttribute] = Field(
        default_factory=list,
        alias="quality-attributes",
    )
    decisions: list[Decision] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return dictionary preserving YAML aliases."""
        return self.model_dump(by_alias=True)

    def all_internal_ids(self) -> set[str]:
        """Return IDs of internal elements including components."""
        ids = {container.id for container in self.containers}
        for container in self.containers:
            ids.update(component.id for component in container.components)
        return ids

    def all_known_ids(self) -> set[str]:
        """Return IDs of all known elements."""
        known = self.all_internal_ids()
        known.update(system.id for system in self.external_systems)
        return known
