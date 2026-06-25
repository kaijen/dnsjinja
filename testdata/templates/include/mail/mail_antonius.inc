; --- Synthetischer selbstgehosteter Mail-Provider "antonius" (Platzhalterwerte) ---
; MX Records
@  IN MX 10 mail.selfhost.example.

; Submission / IMAP / POP SRV
_imap._tcp         IN SRV 1 1 143 mail.selfhost.example.
_imaps._tcp        IN SRV 0 1 993 mail.selfhost.example.
_pop3._tcp         IN SRV 11 1 110 mail.selfhost.example.
_pop3s._tcp        IN SRV 10 1 995 mail.selfhost.example.
_submission._tcp   IN SRV 1 1 587 mail.selfhost.example.
_submissions._tcp  IN SRV 0 1 465 mail.selfhost.example.

; SPF
@ IN TXT "v=spf1 mx -all"

; DKIM (TXT-Record, synthetischer Key)
sel2024._domainkey IN TXT "v=DKIM1; k=rsa; p=MIIBIjANBgkqEXAMPLEKEYDATA00000000000000000000000000000000000000000000000000000000000000000000IDAQAB"
_adsp._domainkey   IN TXT "dkim=discardable"

; Provider-Validation (domänenspezifisch, optional)
{% set include_validation_mailbox = 'include/validation/' + domain + '.inc' %}
{% include include_validation_mailbox ignore missing +%}
