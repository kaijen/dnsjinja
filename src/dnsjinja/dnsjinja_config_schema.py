DNSJINJA_JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft-07/schema",
    "$id": "http://jendrian.eu/schemas/dnsjinijaconfig.json",
    "type": "object",
    "title": "Configuration format for DNSJinja",
    "description": "Schema to validate config.json files for dns-jinja.py (Hetzner Cloud API)",
    "default": {},
    "examples": [
        {
            "global": {
                "zone-files": "zone-files",
                "zone-backups": "zone-backups",
                "templates": "templates",
                "dns-api-base": "https://api.hetzner.cloud/v1",
                "name-servers": [
                    "213.133.100.98",
                    "88.198.229.192",
                    "193.47.99.5"
                ]
            },
            "domains": {
                "secorvo.de": {
                    "template": "secorvo.de.tpl"
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
                "dns-api-base": {
                    "$id": "#/properties/global/properties/dns-api-base",
                    "type": "string",
                    "format": "uri",
                    "pattern": "^https://",
                    "title": "dns-api-base",
                    "description": "Base URL of the Hetzner Cloud API (default: https://api.hetzner.cloud/v1)",
                    "default": "https://api.hetzner.cloud/v1"
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
            "patternProperties": {
                "^.*$": {
                    "$id": "#/properties/domains/properties/domain",
                    "type": "object",
                    "title": "domain",
                    "description": "Name of each domain as key",
                    "default": {},
                    "required": [
                        "template"
                    ],
                    "properties": {
                        "template": {
                            "$id": "#/properties/domains/properties/domain/properties/template",
                            "type": "string",
                            "title": "template",
                            "description": "Starting template for domain",
                            "default": "",
                            "examples": [
                                "secorvo.de.tpl"
                            ]
                        },
                        "zone-file": {
                            "$id": "#/properties/domains/properties/domain/properties/zone-file",
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
