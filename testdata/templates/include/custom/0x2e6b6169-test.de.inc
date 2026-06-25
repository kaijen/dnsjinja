; --- Domänenspezifische Records für die Live-Testdomain (synthetisch) ---
; Hosts
host1 IN A     203.0.113.10
host1 IN AAAA  2001:db8:113::10
host2 IN A     203.0.113.11

; Aliases
dashboard IN CNAME host1
*.apps    IN CNAME host1

; ACME
_acme-challenge IN TXT "synthetic-acme-token-00000000000000000000000000"
