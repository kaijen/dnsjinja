{% set include_www = 'include/www/www_' + www|default('none') + '.inc' %}
{% set include_mail = 'include/mail/mail_' + mail|default('none') + '.inc' %}
{% set include_xmpp = 'include/xmpp/xmpp_' + xmpp|default('none') + '.inc' %}
{% include include_mail ignore missing +%}
{% include include_xmpp ignore missing +%}
{% include include_www ignore missing +%}
{% set include_custom = 'include/custom/' + domain + '.inc' %}
{% include include_custom ignore missing +%}
{% for cg in custom_groups %}
{% set include_custom_group = 'include/custom-groups/' + cg + '.inc' %}
{% include include_custom_group ignore missing +%}
{% endfor %}
registrar IN TXT {{registrar}}
