; MX records
@               IN      MX      10 mx1.mail.example.
@               IN      MX      20 mx2.mail.example.

; Mail client auto-configuration
autoconfig      IN      CNAME   mail.example.
_autodiscover._tcp IN   SRV     0 0 443 mail.example.

; SPF - Sender Policy Framework
@               IN      TXT     "v=spf1 include:mail.example ~all"

; DKIM - DomainKeys Identified Mail
selector1._domainkey    IN      CNAME   selector1._domainkey.mail.example.
selector2._domainkey    IN      CNAME   selector2._domainkey.mail.example.

; DMARC - Domain-based Message Authentication
_dmarc          IN      TXT     "v=DMARC1;p=none;rua=mailto:postmaster@{{domain}}"

; Provider-specific domain validation (if exists)
{% set include_validation_mailbox = 'include/validation/' + domain + '.inc' %}
{% include include_validation_mailbox ignore missing +%}
