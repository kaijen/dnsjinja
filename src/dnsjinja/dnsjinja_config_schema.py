from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class DomainConfig(BaseModel):
    """Konfiguration für eine einzelne Domain (Validierungs-Modell)."""
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    template: str


class GlobalConfig(BaseModel):
    """Globale Konfigurationsoptionen."""
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    zone_files: str = Field(alias='zone-files')
    zone_backups: str = Field(alias='zone-backups')
    templates: str
    name_servers: list[str] = Field(alias='name-servers')

    # Name des DNS-Backends. Bewusst ein freies str statt eines Literal, weil
    # Plugins über Entry-Points weitere Namen beitragen können; ob der Name
    # auflösbar ist, entscheidet die Registry.
    dns_backend: str = Field(
        default='hetzner',
        alias='dns-backend',
        pattern=r'^[a-z0-9][a-z0-9._-]*$',
    )
    # Nicht gesetzt heißt: die Standard-URL des gewählten Backends.
    dns_api_base: str | None = Field(
        default=None,
        alias='dns-api-base',
        pattern=r'^https://',
    )
    # Backendspezifische Schalter, ohne dass das Kernschema sie kennen muss.
    backend_options: dict[str, Any] = Field(
        default_factory=dict,
        alias='backend-options',
    )


class DnsJinjaConfig(BaseModel):
    """Wurzel-Modell zur Validierung von config.json."""
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    global_config: GlobalConfig = Field(alias='global')
    domains: dict[str, DomainConfig]
