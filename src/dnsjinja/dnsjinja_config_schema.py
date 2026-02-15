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
    dns_api_base: str = Field(
        default='https://api.hetzner.cloud/v1',
        alias='dns-api-base',
        pattern=r'^https://',
    )


class DnsJinjaConfig(BaseModel):
    """Wurzel-Modell zur Validierung von config.json."""
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    global_config: GlobalConfig = Field(alias='global')
    domains: dict[str, DomainConfig]
