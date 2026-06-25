; --- Synthetischer Mail-Provider "mailbox.org" (Platzhalterwerte) ---
; MX Records
@  IN MX 10 mx1.mailprovider.example.
@  IN MX 20 mx2.mailprovider.example.

; Autoconfig / Autodiscover
autoconfig          IN CNAME mailprovider.example.
_autodiscover._tcp  IN SRV 0 0 443 mailprovider.example.

; SPF
@ IN TXT "v=spf1 include:mailprovider.example ~all"

; DKIM (CNAME-Delegation an den Provider)
sel1._domainkey  IN CNAME sel1._domainkey.mailprovider.example.
sel2._domainkey  IN CNAME sel2._domainkey.mailprovider.example.

; DMARC
_dmarc IN TXT "v=DMARC1; p=none; rua=mailto:postmaster@{{domain}}"

; Provider-Validation (domänenspezifisch, optional)
{% set include_validation_mailbox = 'include/validation/' + domain + '.inc' %}
{% include include_validation_mailbox ignore missing +%}
