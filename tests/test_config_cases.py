"""Offline-Render-Tests für alle sinnvollen Domain-Konfigurationen.

Diese Tests benötigen kein Netzwerk: Hetzner-Client und DNS-Resolver sind
gemockt (siehe conftest.build_dj). Geprüft wird der gesamte Render-Pfad der
echten DNSJinja-Klasse inklusive _parse_zone_rrsets() – also genau die
Datenstruktur, die später an die Hetzner-RRSet-API übergeben wird.

Die verwendeten Templates liegen im eingecheckten testdata/-Verzeichnis.
"""
import json

import jinja2
import pytest

from tests.conftest import TESTDATA_DIR

T = "standard.tpl"


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def rrsets(dj, domain):
    """{(name, type): (ttl, [values])} der gerenderten Zone (ohne SOA)."""
    return dj._parse_zone_rrsets(domain)


def keys(dj, domain):
    return set(rrsets(dj, domain).keys())


def dom(**extra):
    """Domain-Konfig mit Pflichtfeldern template + registrar."""
    return {"template": T, "registrar": "Hetzner", **extra}


# ---------------------------------------------------------------------------
# Grundgerüst: NS, SOA, registrar
# ---------------------------------------------------------------------------

class TestMinimal:

    def test_minimal_nur_ns_und_registrar(self, build_dj):
        dj = build_dj({"minimal.example": dom()})
        k = keys(dj, "minimal.example")
        assert ("@", "NS") in k
        assert ("registrar", "TXT") in k
        # Keine optionalen Records
        assert ("@", "A") not in k
        assert ("@", "MX") not in k

    def test_soa_wird_nicht_als_rrset_geliefert(self, build_dj):
        """SOA wird von Hetzner verwaltet und aus dem RRSet-Sync ausgeschlossen."""
        dj = build_dj({"minimal.example": dom()})
        assert ("@", "SOA") not in keys(dj, "minimal.example")
        # ... ist aber im gerenderten Zonentext vorhanden
        assert "IN\tSOA" in dj.zones["minimal.example"] or "IN SOA" in dj.zones["minimal.example"]

    def test_registrar_wert_wird_gerendert(self, build_dj):
        dj = build_dj({"d.example": dom(registrar="Namecheap")})
        ttl, vals = rrsets(dj, "d.example")[("registrar", "TXT")]
        assert vals == ['"Namecheap"']

    def test_ns_default_ist_hetzner(self, build_dj):
        dj = build_dj({"d.example": dom()})
        _, vals = rrsets(dj, "d.example")[("@", "NS")]
        assert "hydrogen.ns.hetzner.com." in vals


# ---------------------------------------------------------------------------
# mail-Provider
# ---------------------------------------------------------------------------

class TestMail:

    def test_mailbox_org(self, build_dj):
        dj = build_dj({"mailbox.example": dom(mail="mailbox.org")})
        rr = rrsets(dj, "mailbox.example")
        assert rr[("@", "MX")][1] == [
            "10 mx1.mailprovider.example.",
            "20 mx2.mailprovider.example.",
        ]
        assert ("autoconfig", "CNAME") in rr
        assert ("_dmarc", "TXT") in rr
        assert ("sel1._domainkey", "CNAME") in rr
        # SPF
        assert any("v=spf1" in v for v in rr[("@", "TXT")][1])
        # domänenspezifische Validation wird vom mail-Include nachgeladen
        assert ("_provider-verify", "TXT") in rr

    def test_antonius(self, build_dj):
        dj = build_dj({"antonius.example": dom(mail="antonius")})
        rr = rrsets(dj, "antonius.example")
        assert rr[("@", "MX")][1] == ["10 mail.selfhost.example."]
        assert ("_submission._tcp", "SRV") in rr
        assert ("sel2024._domainkey", "TXT") in rr
        # antonius hat keine Validation-Datei -> kein _provider-verify
        assert ("_provider-verify", "TXT") not in rr

    def test_spamhero_mehrere_mx(self, build_dj):
        dj = build_dj({"spamhero.example": dom(mail="spamhero")})
        rr = rrsets(dj, "spamhero.example")
        assert len(rr[("@", "MX")][1]) == 3

    def test_unbekannter_mail_provider_wird_ignoriert(self, build_dj):
        """Fehlender mail-Include (ignore missing) -> kein Fehler, keine MX."""
        dj = build_dj({"x.example": dom(mail="gibtsnicht")})
        k = keys(dj, "x.example")
        assert ("@", "MX") not in k
        assert ("@", "NS") in k  # Rest rendert normal


# ---------------------------------------------------------------------------
# www-Provider
# ---------------------------------------------------------------------------

class TestWww:

    def test_bero_single_a(self, build_dj):
        dj = build_dj({"w.example": dom(www="bero")})
        rr = rrsets(dj, "w.example")
        assert rr[("@", "A")][1] == ["192.0.2.10"]
        assert rr[("www", "A")][1] == ["192.0.2.10"]

    def test_adobe_mehrere_a(self, build_dj):
        dj = build_dj({"w.example": dom(www="adobe")})
        rr = rrsets(dj, "w.example")
        assert sorted(rr[("@", "A")][1]) == ["198.51.100.20", "198.51.100.21"]

    def test_beromjh_a_und_aaaa(self, build_dj):
        dj = build_dj({"w.example": dom(www="beromjh")})
        rr = rrsets(dj, "w.example")
        assert rr[("@", "A")][1] == ["192.0.2.30"]
        assert rr[("@", "AAAA")][1] == ["2001:db8::30"]


# ---------------------------------------------------------------------------
# xmpp
# ---------------------------------------------------------------------------

class TestXmpp:

    def test_xmpp_srv_records(self, build_dj):
        dj = build_dj({"x.example": dom(xmpp="mailbox")})
        rr = rrsets(dj, "x.example")
        assert ("_xmpp-client._tcp", "SRV") in rr
        assert ("_xmpp-server._tcp", "SRV") in rr

    def test_xmpp_ttl_ist_300(self, build_dj):
        """XMPP-Records erben den Zonen-TTL von 300s (kein Override mehr)."""
        dj = build_dj({"x.example": dom(xmpp="mailbox")})
        ttl, _ = rrsets(dj, "x.example")[("_xmpp-client._tcp", "SRV")]
        assert ttl == 300


# ---------------------------------------------------------------------------
# custom / custom_groups
# ---------------------------------------------------------------------------

class TestCustom:

    def test_custom_per_domain_include(self, build_dj):
        dj = build_dj({"custom.example": dom()})
        rr = rrsets(dj, "custom.example")
        assert rr[("@", "A")][1] == ["203.0.113.50"]
        # interner CNAME wird relativ ausgegeben
        assert rr[("intra", "CNAME")][1] == ["www"]

    def test_custom_fehlt_wird_ignoriert(self, build_dj):
        """Domain ohne custom/<domain>.inc rendert ohne Fehler."""
        dj = build_dj({"ohne-custom.example": dom()})
        assert ("@", "A") not in keys(dj, "ohne-custom.example")

    def test_custom_groups(self, build_dj):
        dj = build_dj({"g.example": dom(www="bero", custom_groups=["demo-group"])})
        rr = rrsets(dj, "g.example")
        assert rr[("status", "CNAME")][1] == ["www"]
        assert rr[("webmail", "CNAME")][1] == ["www"]

    def test_unbekannte_custom_group_wird_ignoriert(self, build_dj):
        dj = build_dj({"g.example": dom(custom_groups=["gibtsnicht"])})
        assert ("status", "CNAME") not in keys(dj, "g.example")


# ---------------------------------------------------------------------------
# subdomains
# ---------------------------------------------------------------------------

class TestSubdomains:

    def test_subdomain_meta_wird_gerendert(self, build_dj):
        dj = build_dj({"subs.example": dom(mail="mailbox.org",
                                           subdomains=["shop", "blog"])})
        k = keys(dj, "subs.example")
        # Subdomains bekommen ihren eigenen Mail-Block (relativ zum Subdomain-Origin)
        assert ("shop", "MX") in k
        assert ("blog", "MX") in k
        assert ("registrar.shop", "TXT") in k

    def test_ohne_subdomains_keine_subrecords(self, build_dj):
        dj = build_dj({"subs.example": dom(mail="mailbox.org")})
        assert ("shop", "MX") not in keys(dj, "subs.example")


# ---------------------------------------------------------------------------
# ns / soa Override
# ---------------------------------------------------------------------------

class TestNsSoaOverride:

    def test_ns_override(self, build_dj):
        dj = build_dj({"d.example": dom(ns="external")})
        _, vals = rrsets(dj, "d.example")[("@", "NS")]
        assert vals == [
            "ns1.external-registrar.example.",
            "ns2.external-registrar.example.",
        ]

    def test_ns_override_ohne_include_schlaegt_fehl(self, build_dj):
        """ns/soa werden ohne 'ignore missing' eingebunden -> TemplateNotFound."""
        with pytest.raises(jinja2.exceptions.TemplateNotFound):
            build_dj({"d.example": dom(ns="existiert-nicht")})


# ---------------------------------------------------------------------------
# Kombinationen
# ---------------------------------------------------------------------------

class TestKombinationen:

    def test_full_feature(self, build_dj):
        dj = build_dj({"full.example": dom(
            mail="mailbox.org", www="beromjh", xmpp="mailbox",
            custom_groups=["demo-group"],
        )})
        rr = rrsets(dj, "full.example")
        for key in [("@", "NS"), ("@", "A"), ("@", "AAAA"), ("@", "MX"),
                    ("@", "TXT"), ("_dmarc", "TXT"),
                    ("_xmpp-client._tcp", "SRV"), ("autoconfig", "CNAME"),
                    ("status", "CNAME"), ("registrar", "TXT")]:
            assert key in rr, f"{key} fehlt"

    def test_mehrere_domains_gleichzeitig(self, build_dj):
        dj = build_dj({
            "a.example": dom(www="bero"),
            "b.example": dom(mail="mailbox.org"),
        })
        assert "a.example" in dj.zones and "b.example" in dj.zones
        assert ("@", "A") in keys(dj, "a.example")
        assert ("@", "MX") in keys(dj, "b.example")


# ---------------------------------------------------------------------------
# Fehlerfälle in der Konfiguration
# ---------------------------------------------------------------------------

class TestFehlerfaelle:

    def test_fehlendes_template_feld(self, build_dj):
        with pytest.raises(SystemExit):
            build_dj({"d.example": {"registrar": "Hetzner"}})

    def test_ungueltiger_template_name(self, build_dj):
        with pytest.raises(SystemExit):
            build_dj({"d.example": {"template": "../evil.tpl", "registrar": "X"}})


# ---------------------------------------------------------------------------
# Smoke-Test über die eingecheckte testdata/config.json
# ---------------------------------------------------------------------------

class TestShippedConfig:

    def test_alle_konfigurierten_domains_rendern(self, build_dj):
        """Jede Domain aus testdata/config/config.json rendert zu gültigem
        BIND-Zonentext und lässt sich in RRSets parsen."""
        cfg = json.loads((TESTDATA_DIR / "config" / "config.json").read_text())
        domains = cfg["domains"]
        dj = build_dj(domains)
        for name in domains:
            assert name in dj.zones
            rr = rrsets(dj, name)  # parst dns.zone.from_text – wirft bei Syntaxfehler
            assert ("@", "NS") in rr
            assert ("registrar", "TXT") in rr


class TestTtl:
    """Der TTL aller verwalteten Records muss einheitlich 300s betragen."""

    def test_alle_rrsets_haben_ttl_300(self, build_dj):
        cfg = json.loads((TESTDATA_DIR / "config" / "config.json").read_text())
        domains = cfg["domains"]
        dj = build_dj(domains)
        offending = []
        for name in domains:
            for (rname, rtype), (ttl, _) in rrsets(dj, name).items():
                if ttl != 300:
                    offending.append((name, rname, rtype, ttl))
        assert not offending, f"Records mit TTL != 300: {offending}"

    @pytest.mark.parametrize("features", [
        {},
        {"mail": "mailbox.org"},
        {"mail": "antonius"},
        {"mail": "spamhero"},
        {"www": "adobe"},
        {"www": "beromjh"},
        {"xmpp": "mailbox"},
        {"custom_groups": ["demo-group"], "www": "bero"},
        {"subdomains": ["shop", "blog"], "mail": "mailbox.org"},
    ])
    def test_ttl_300_fuer_jede_feature_kombination(self, build_dj, features):
        dj = build_dj({"d.example": dom(**features)})
        ttls = {ttl for (ttl, _) in rrsets(dj, "d.example").values()}
        assert ttls == {300}, f"Unerwartete TTLs: {ttls}"
