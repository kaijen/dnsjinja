{% include 'include/00-ttl.inc' +%}
{% include 'include/00-meta.inc' +%}
{% set org_domain = domain %}
{% for dom in subdomains %}
{% set domain = dom + '.' + org_domain %}
{% include 'include/00-ttl.inc' +%}
{% include 'include/00-subdomain-meta.inc' +%}

{% endfor %}
