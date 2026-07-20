# Beispiel: Eine Domain zusammensetzen

Dieser Walkthrough zeigt Schritt für Schritt, wie aus einem Konfigurationseintrag und
den modularen Includes ein vollständiges Zone-File entsteht. Alle Daten sind
anonymisiert (`example.com`, RFC-5737-Adressen wie `198.51.100.x`, `2001:db8::/32`) und
stammen aus dem mitgelieferten Datensatz
[`samples/`](https://github.com/kaijen/dnsjinja/tree/main/samples).

## Der Konfigurationseintrag

```json
"example.com": {
  "template": "standard.tpl",
  "mail": "example-provider",
  "www": "example-provider",
  "xmpp": "example-provider",
  "registrar": "Hetzner",
  "subdomains": ["blog", "dev"],
  "custom_groups": ["shared-hosting"]
}
```

Aus diesem Eintrag entscheidet `dnsjinja`, welche Includes eingebunden werden:

| Feld | Wert | eingebundener Include |
|------|------|-----------------------|
| `mail` | `example-provider` | `include/mail/mail_example-provider.inc` |
| `www` | `example-provider` | `include/www/www_example-provider.inc` |
| `xmpp` | `example-provider` | `include/xmpp/xmpp_example-provider.inc` |
| (Domainname) | `example.com` | `include/custom/example.com.inc` (automatisch) |
| `custom_groups` | `shared-hosting` | `include/custom-groups/shared-hosting.inc` |
| (aus Mail-Include) | `example.com` | `include/validation/example.com.inc` (falls vorhanden) |
| `registrar` | `Hetzner` | TXT-Record `registrar` (nur am Apex) |
| `subdomains` | `blog`, `dev` | je ein eigener Zonen-Abschnitt |

SOA und NS kommen aus den Standard-Providern (`soa_hetzner`, `ns_hetzner`), da kein
`soa`/`ns`-Override gesetzt ist.

## Die Bausteine

=== "mail_example-provider.inc"

    ```dns
    ; MX records
    @               IN      MX      10 mx1.mail.example.
    @               IN      MX      20 mx2.mail.example.

    ; Mail client auto-configuration
    autoconfig      IN      CNAME   mail.example.
    _autodiscover._tcp IN   SRV     0 0 443 mail.example.

    ; SPF
    @               IN      TXT     "v=spf1 include:mail.example ~all"

    ; DKIM
    selector1._domainkey  IN  CNAME  selector1._domainkey.mail.example.
    selector2._domainkey  IN  CNAME  selector2._domainkey.mail.example.

    ; DMARC
    _dmarc          IN      TXT     "v=DMARC1;p=none;rua=mailto:postmaster@{{domain}}"

    ; bindet validation/<domain>.inc ein, falls vorhanden
    {% set inc = 'include/validation/' + domain + '.inc' %}
    {% include inc ignore missing +%}
    ```

=== "www_example-provider.inc"

    ```dns
    ; Web server A records
    @               IN      A       198.51.100.10
    www             IN      A       198.51.100.10
    ```

=== "xmpp_example-provider.inc"

    ```dns
    ; XMPP/Jabber SRV records
    _xmpp-client._tcp  3600  IN  SRV  0 5 5222 xmpp.example.
    _xmpp-server._tcp  3600  IN  SRV  0 5 5269 xmpp.example.
    ```

=== "custom/example.com.inc"

    ```dns
    ; Domain-specific custom records for example.com
    calendar        IN      CNAME   ghs.example.
    docs            IN      CNAME   ghs.example.
    vpn             IN      A       198.51.100.20
    vpn             IN      AAAA    2001:db8::20
    ```

=== "custom-groups/shared-hosting.inc"

    ```dns
    ; Shared hosting (mehrfach verwendbar)
    @               3600    IN      A       198.51.100.50
    *               3600    IN      CNAME   {{domain}}.
    webmail         3600    IN      CNAME   www
    ```

=== "validation/example.com.inc"

    ```dns
    ; Domain ownership validation (provider-spezifisch)
    a1b2c3d4e5f6    IN      TXT     "verification=abc123def456"
    ```

`{{domain}}` wird beim Rendern durch den aktuellen Domainnamen ersetzt – bei der
Hauptdomain `example.com.`, bei der Subdomain `blog.example.com.` usw. So funktioniert
derselbe Baustein (etwa die `*`-Wildcard der Shared Group) für Haupt- und Subdomains.

## Das gerenderte Zone-File

`dnsjinja -d samples -c samples/config.json.sample --dry-run` erzeugt für die
Hauptdomain:

```dns title="example.com (Hauptdomain)"
$ORIGIN example.com.
$TTL 300
; SOA record for Hetzner DNS
@		IN	SOA	hydrogen.ns.hetzner.com. dns.hetzner.com. 2026010101 86400 10800 3600000 3600
; Hetzner nameservers
@		IN	NS	helium.ns.hetzner.de.
@		IN	NS	hydrogen.ns.hetzner.com.
@		IN	NS	oxygen.ns.hetzner.com.
; Registrar der registrierten Domäne
registrar IN TXT "Hetzner"
; MX records
@               IN      MX      10 mx1.mail.example.
@               IN      MX      20 mx2.mail.example.
; Mail client auto-configuration
autoconfig      IN      CNAME   mail.example.
_autodiscover._tcp IN   SRV     0 0 443 mail.example.
; SPF
@               IN      TXT     "v=spf1 include:mail.example ~all"
; DKIM
selector1._domainkey    IN      CNAME   selector1._domainkey.mail.example.
selector2._domainkey    IN      CNAME   selector2._domainkey.mail.example.
; DMARC
_dmarc          IN      TXT     "v=DMARC1;p=none;rua=mailto:postmaster@example.com"
; Domain ownership validation
a1b2c3d4e5f6    IN      TXT     "verification=abc123def456"
; XMPP
_xmpp-client._tcp      3600    IN      SRV     0 5 5222 xmpp.example.
_xmpp-server._tcp      3600    IN      SRV     0 5 5269 xmpp.example.
; Web server
@               IN      A       198.51.100.10
www             IN      A       198.51.100.10
; custom/example.com.inc
calendar        IN      CNAME   ghs.example.
docs            IN      CNAME   ghs.example.
vpn             IN      A       198.51.100.20
vpn             IN      AAAA    2001:db8::20
; custom-groups/shared-hosting.inc
@               3600    IN      A       198.51.100.50
*               3600    IN      CNAME   example.com.
webmail         3600    IN      CNAME   www
```

Direkt im Anschluss folgen die Subdomains. Sie durchlaufen dieselben Provider-Includes,
aber mit angepasstem `$ORIGIN` – und ohne SOA/NS, da diese nur zur Hauptzone gehören.
Auch der `registrar`-Record fehlt: Registriert wird die Domäne, nicht die Subdomäne.

```dns title="blog.example.com (Subdomain, gekürzt)"
$ORIGIN blog.example.com.
$TTL 300
@               IN      MX      10 mx1.mail.example.
@               IN      MX      20 mx2.mail.example.
autoconfig      IN      CNAME   mail.example.
...
@               3600    IN      A       198.51.100.50
*               3600    IN      CNAME   blog.example.com.
webmail         3600    IN      CNAME   www
```

## Die anderen beiden Beispiel-Domains

**`example.org`** (Mail + Web, kein XMPP, keine Subdomains, kein Custom):

```dns
$ORIGIN example.org.
$TTL 300
@	IN	SOA	hydrogen.ns.hetzner.com. dns.hetzner.com. 2026010101 86400 10800 3600000 3600
@	IN	NS	helium.ns.hetzner.de.
@	IN	NS	hydrogen.ns.hetzner.com.
@	IN	NS	oxygen.ns.hetzner.com.
registrar IN TXT "Namecheap"
@   IN MX 10 mx1.mail.example.
@   IN MX 20 mx2.mail.example.
autoconfig          IN CNAME mail.example.
_autodiscover._tcp  IN SRV   0 0 443 mail.example.
@   IN TXT "v=spf1 include:mail.example ~all"
selector1._domainkey IN CNAME selector1._domainkey.mail.example.
selector2._domainkey IN CNAME selector2._domainkey.mail.example.
_dmarc IN TXT "v=DMARC1;p=none;rua=mailto:postmaster@example.org"
@   IN A 198.51.100.10
www IN A 198.51.100.10
```

**`example.net`** (geparkt – nur SOA, NS und Registrar):

```dns
$ORIGIN example.net.
$TTL 300
@	IN	SOA	hydrogen.ns.hetzner.com. dns.hetzner.com. 2026010101 86400 10800 3600000 3600
@	IN	NS	helium.ns.hetzner.de.
@	IN	NS	hydrogen.ns.hetzner.com.
@	IN	NS	oxygen.ns.hetzner.com.
registrar IN TXT "GoDaddy"
```

## Eigene Daten ableiten

Um daraus eine echte Konfiguration zu machen:

1. `samples/` kopieren und die Platzhalter-Domains durch eigene ersetzen.
2. Pro Mail-/Web-/XMPP-Provider den passenden Include unter `include/<kategorie>/`
   anlegen (siehe [Template-Architektur](templates.md#neuen-provider-hinzufugen)).
3. Domain-spezifische Records in `include/custom/<domain>.inc`, geteilte in
   `include/custom-groups/<name>.inc`.
4. Mit `--dry-run` prüfen, dann mit `-b -w -u` ausspielen
   (siehe [Schnellstart](schnellstart.md)).
