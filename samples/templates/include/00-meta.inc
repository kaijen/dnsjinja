{% set include_ns = 'include/ns/ns_' + ns|default('hetzner') + '.inc' %}
{% set include_soa = 'include/soa/soa_' + soa|default('hetzner') + '.inc' %}
{% include include_soa +%}
{% include include_ns +%}
{% include 'include/00-subdomain-meta.inc' +%}
