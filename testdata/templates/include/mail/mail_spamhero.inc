; --- Synthetischer Filter-Mail-Provider "spamhero" (Platzhalterwerte) ---
; MX Records
@ IN MX 10 mx-a.filter.example.
@ IN MX 20 mx-b.filter.example.
@ IN MX 30 mx-c.filter.example.

; SPF
@ IN TXT "v=spf1 include:filter.example -all"

; Provider-Validation (domänenspezifisch, optional)
{% set include_validation_mailbox = 'include/validation/' + domain + '.inc' %}
{% include include_validation_mailbox ignore missing +%}
