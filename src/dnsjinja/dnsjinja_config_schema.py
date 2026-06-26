from pydantic import BaseModel, Field, ConfigDict, model_validator


class DomainConfig(BaseModel):
    """Konfiguration für eine einzelne Domain (Validierungs-Modell)."""
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    template: str
    # Optionaler Verweis auf einen Provider aus global.providers (Multiprovider, #10).
    provider: str | None = None


class ProviderDef(BaseModel):
    """Definition eines benannten DNS-Providers (Multiprovider, #10)."""
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    plugin: str
    api_base: str | None = Field(default=None, alias='api-base')
    token_env: str | None = Field(default=None, alias='token-env')


class GlobalConfig(BaseModel):
    """Globale Konfigurationsoptionen."""
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    zone_files: str = Field(alias='zone-files')
    zone_backups: str = Field(alias='zone-backups')
    templates: str
    name_servers: list[str] = Field(alias='name-servers')
    # Legacy-Single-Provider-Feld: API-Endpoint (provider-spezifischer Default).
    dns_api_base: str = Field(
        default='https://api.hetzner.cloud/v1',
        alias='dns-api-base',
        pattern=r'^https://',
    )
    # Legacy: Plugin-Kennung für den impliziten Single-Provider (Default hetzner).
    provider: str | None = None
    # Multiprovider (#10): benannte Provider-Definitionen + Default.
    providers: dict[str, ProviderDef] | None = None
    default_provider: str | None = Field(default=None, alias='default-provider')


class DnsJinjaConfig(BaseModel):
    """Wurzel-Modell zur Validierung von config.json."""
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    global_config: GlobalConfig = Field(alias='global')
    domains: dict[str, DomainConfig]

    @model_validator(mode='after')
    def _check_provider_references(self) -> 'DnsJinjaConfig':
        providers = self.global_config.providers
        provider_names = set(providers) if providers else set()

        default_provider = self.global_config.default_provider
        if default_provider and default_provider not in provider_names:
            raise ValueError(
                f"default-provider {default_provider!r} ist nicht in global.providers definiert")

        for domain, dcfg in self.domains.items():
            if dcfg.provider is None:
                continue
            if not providers:
                raise ValueError(
                    f"Domain {domain!r} verweist auf Provider {dcfg.provider!r}, "
                    f"aber global.providers ist nicht definiert")
            if dcfg.provider not in provider_names:
                raise ValueError(
                    f"Domain {domain!r} verweist auf unbekannten Provider {dcfg.provider!r}. "
                    f"Verfügbar: {', '.join(sorted(provider_names))}")

        if providers and not default_provider and len(providers) > 1:
            # Domains ohne expliziten Provider brauchen einen Default.
            domains_without = [d for d, c in self.domains.items() if c.provider is None]
            if domains_without:
                raise ValueError(
                    "Mehrere Provider konfiguriert, aber kein default-provider; "
                    f"Domains ohne provider-Feld: {', '.join(sorted(domains_without))}")
        return self
