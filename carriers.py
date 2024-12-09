# custom_components/parcel_tracking_info/carriers.py

CARRIER_TEMPLATES = {
    'DHL': {
        'name': 'DHL',
        'api_url': 'https://api-eu.dhl.com/track/shipments',
        'search_criteria': '(FROM "dhl")',
        'tracking_pattern': r"\b\d{12}\b|\b\d{20}\b|\bJJD\d{12,24}\b",
        'carrier': 'DHL',
        'email_parsing': {
            'eta_string': 'geplant für ',
            'eta_date_pattern': r"(?i)(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s+\d{1,2}\s+(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)",
            'status_strings': ['in transit', 'in delivery', 'out for delivery', 'in zustellung', 'wird zugestellt', 'unterwegs', 'in Kürze zugestellt', 'sendung unterwegs', 'in zustellung', 'wird zugestellt', 'abholbereit']
        },
        'tracking_link_url': 'https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?lang=de&idc='
    },
    'hermes': {
        'name': 'Hermes',
        'api_url': '',  # If Hermes provides an API, add the URL here
        'search_criteria': '(FROM "myhermes")',
        'tracking_pattern': r"\b(H\d{19}|\d{14})\b",
        'carrier': 'Hermes',
        'email_parsing': {
            'eta_string': 'Voraussichtliche Zustellung am',
            'eta_date_pattern': r"\d{2}\.\d{2}\.\d{4}",
            'status_strings': ['in transit', 'in delivery', 'out for delivery', 'in zustellung', 'wird zugestellt', 'unterwegs', 'in Kürze zugestellt', 'sendung unterwegs', 'in zustellung', 'wird zugestellt', 'abholbereit']
        },
        'tracking_link_url': 'https://www.myhermes.de/empfangen/sendungsverfolgung/?suche='
    },
    'amazon': {
        'name': 'Amazon',
        'api_url': '',  # If Amazon provides an API, add the URL here
        'search_criteria': '(FROM "amazon")',
        'tracking_pattern': r"\bDE\d{10}\b",
        'carrier': 'Amazon',
        'email_parsing': {
            'eta_string': 'Zustellung:',
            'eta_date_pattern': r"\\w+,\\s+\\d{1,2}\\s+\\w+",
            'status_strings': ['in transit', 'in delivery', 'out for delivery', 'in zustellung', 'wird zugestellt', 'unterwegs', 'in Kürze zugestellt', 'sendung unterwegs', 'in zustellung', 'wird zugestellt', 'abholbereit']
        }
    },
    'DPD': {
        'name': 'DPD',
        'api_url': 'none',
        'search_criteria': '(FROM "dpd")',
        'tracking_pattern': r'\b\d{14}\b',
        'carrier': 'DPD',
        'email_parsing': {  # Added empty email_parsing
            'eta_string': 'Ihre Sendung stellen wir in',
            'eta_date_pattern': '(\d+)-(\d+)\s+Werktagen',
            'status_strings': ['stellen wir', 'in transit', 'in delivery', 'out for delivery', 'in zustellung', 'wird zugestellt', 'unterwegs', 'in Kürze zugestellt', 'sendung unterwegs', 'in zustellung', 'wird zugestellt', 'abholbereit']
        },
        'tracking_link_url': 'https://my.dpd.de/myparcels/dataprotection.aspx?action=2&parcelno=B2C0'
    },
    'GLS': {
        'name': 'GLS',
        'api_url': 'none',
        'search_criteria': '(FROM "gls")',
        'tracking_pattern': r'\b\d{11}\b',
        'carrier': 'GLS',
        'email_parsing': {  # Added empty email_parsing
            'eta_string': '',
            'eta_date_pattern': '',
            'status_strings': ['in transit', 'in delivery', 'out for delivery', 'in zustellung', 'wird zugestellt', 'unterwegs', 'in Kürze zugestellt', 'sendung unterwegs', 'in zustellung', 'wird zugestellt', 'abholbereit']
        },
    },     
    
}

def add_custom_carrier(name, api_url="", search_criteria='', tracking_pattern='', email_parsing=None, tracking_link_url=''):
    """Add a custom carrier to CARRIER_TEMPLATES."""
    CARRIER_TEMPLATES[name.upper()] = {
        'name': name.lower(),
        'api_url': api_url,
        'search_criteria': search_criteria or f'(FROM "{name}")',
        'tracking_pattern': tracking_pattern or r"",
        'email_parsing': email_parsing or {
            'eta_string': '',
            'eta_date_pattern': '',
            'status_strings': []
        },
        'tracking_link_url': tracking_link_url
    }