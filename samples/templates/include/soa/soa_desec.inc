; SOA record for deSEC
; deSEC pflegt den SOA-Record selbst; dieser Eintrag dient nur der lokalen
; Zonefile-Validierung und wird beim Upload nicht übertragen.
@		IN	SOA	ns1.desec.io. hostmaster.example.com. {{ soa_serial }} 86400 10800 3600000 3600
