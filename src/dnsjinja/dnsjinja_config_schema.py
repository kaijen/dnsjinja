DNSJINJA_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema",
    "$id": "http://jendrian.eu/schemas/dnsjinijaconfig.json",
    "type": "object",
    "title": "Configuration format for DNSJinja",
    "description": "Schema to validate config.json files for dns-jinja.py",
    "default": {},
    "examples": [
        {
            "global": {
                "zone-files": "zone-files",
                "zone-backups": "zone-backups",
                "templates": "templates",
                "dns-upload-api": "https://dns.hetzner.com/api/v1/zones/{ZoneID}/import",
                "dns-download-api": "https://dns.hetzner.com/api/v1/zones/{ZoneID}/export",
                "name-servers": [
                    "213.133.100.98",
                    "88.198.229.192",
                    "193.47.99.5"
                ]
            },
            "domains": {
                "secorvo.de": {
                    "zone-id": "D4Gv7yqGJenJhFk8hTENcb",
                    "template": "secorvo.de.tpl",
                    "zone-file": "secorvo.de.zone"
                }
            }
        }
    ],
    "required": [
        "global",
        "domains"
    ],
    "properties": {
        "global": {
            "$id": "#/properties/global",
            "type": "object",
            "title": "global configuration options",
            "description": "The parameters which are configured globally for dns-jinja.py",
            "default": {},
            "required": [
                "zone-files",
                "zone-backups",
                "templates",
                "dns-upload-api",
                "dns-download-api",
                "dns-zones-api",
                "name-servers"
            ],
            "properties": {
                "zone-files": {
                    "$id": "#/properties/global/properties/zone-files",
                    "type": "string",
                    "title": "zone-files",
                    "description": "Location of zone files to be written by dns-jinja.py",
                    "default": ""
                },
                "zone-backups": {
                    "$id": "#/properties/global/properties/zone-backups",
                    "type": "string",
                    "title": "zone-backups",
                    "description": "Location of backup zone files to be written by dns-jinja.py",
                    "default": ""
                },
                "templates": {
                    "$id": "#/properties/global/properties/templates",
                    "type": "string",
                    "title": "templates",
                    "description": "Location of Jinja2 template files for dns-jinja.py",
                    "default": ""
                },
                "dns-upload-api": {
                    "$id": "#/properties/global/properties/dns-upload-api",
                    "type": "string",
                    "format": "uri",
                    "pattern": "^https?://",
                    "title": "dns-upload-api",
                    "description": "URL to upload zone data to",
                    "default": ""
                },
                "dns-download-api": {
                    "$id": "#/properties/global/properties/dns-download-api",
                    "type": "string",
                    "format": "uri",
                    "pattern": "^https?://",
                    "title": "The dns-download-api",
                    "description": "URL to download zone data from",
                    "default": ""
                },
                "dns-zones-api": {
                    "$id": "#/properties/global/properties/dns-zones-api",
                    "type": "string",
                    "format": "uri",
                    "pattern": "^https?://",
                    "title": "The dns-zones-api",
                    "description": "URL to download all zones",
                    "default": ""
                },
                "name-servers": {
                    "$id": "#/properties/global/properties/name-servers",
                    "type": "array",
                    "title": "name-servers schema",
                    "description": "Name servers to ask for SOA serial",
                    "default": [],
                    "additionalItems": True,
                    "items": {
                        "$id": "#/properties/global/properties/name-servers/items",
                        "anyOf": [
                            {
                                "$id": "#/properties/global/properties/name-servers/items/anyOf/0",
                                "type": "string",
                                "title": "name-servers",
                                "description": "Name server IP address",
                                "format": "ipv4",
                                "default": ""
                            }
                        ]
                    }
                }
            },
            "additionalProperties": True
        },
        "domains": {
            "$id": "#/properties/domains",
            "type": "object",
            "title": "domains",
            "description": "All the domains to be handled by dns-jinja.py",
            "default": {},
            "pattern_properties": {
                "\"^.*$\"": {
                    "$id": "#/properties/domains/properties/domain",
                    "type": "object",
                    "title": "domain",
                    "description": "Name of each domain as key",
                    "default": {},
                    "required": [
                        "template",
                        "zone-id"
                    ],
                    "properties": {
                        "zone-id": {
                            "$id": "#/properties/domains/properties/secorvo.de/properties/zone-id",
                            "type": "string",
                            "title": "zone-id",
                            "description": "Zone-ID as provided by Hetzner",
                            "default": "",
                            "examples": [
                                "D4Gv7yqGJenJhFk8hTENcb"
                            ]
                        },
                        "template": {
                            "$id": "#/properties/domains/properties/secorvo.de/properties/template",
                            "type": "string",
                            "title": "template",
                            "description": "Starting template for domain",
                            "default": "",
                            "examples": [
                                "secorvo.de.tpl"
                            ]
                        },
                        "zone-file": {
                            "$id": "#/properties/domains/properties/secorvo.de/properties/zone-file",
                            "type": "string",
                            "title": "zone-file",
                            "description": "Output file name for zone-file",
                            "default": "",
                            "examples": [
                                "secorvo.de.zone"
                            ]
                        }
                    },
                    "additionalProperties": True
                }
            },
            "additionalProperties": True
        }
    },
    "additionalProperties": True
}