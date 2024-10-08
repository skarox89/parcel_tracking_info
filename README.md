# Introduction
The Parcel Tracking Info integration allows you to track your parcels directly within Home Assistant by parsing emails from various carriers and optionally fetching additional tracking information via carrier APIs. This integration supports multiple carriers and provides real-time updates on the status of your shipments.

# Important
- The integration is primarily based on german carriers, i.e. the regex used in the carrier templates might not properly reflect the tracking codes in your area. Either use custom integration or raise an issue, I will then add the carrier regex asap.
- API access currently only is implemented for DHL.

# Features
- Email Parsing: Extract tracking numbers, estimated delivery dates, and status updates from carrier emails.
- API Integration: Fetch detailed tracking information from carrier APIs for supported carriers.
- Multiple Carriers Support: Easily configure and track shipments from carriers like DHL, GLS, Hermes, DPD, and custom carriers.
- Customizable Parsing Rules: Define custom regex patterns and parsing rules to extract information specific to your carrier.
- Flexible Configuration: Edit carrier names, display names, and other settings through the integration's options flow.
- Notifications: Receive updates on your shipments directly within Home Assistant.

# Installation
Prerequisites
- Home Assistant Core 2023.1 or later.
- An email account accessible via IMAP.
- API keys for carriers (if using API integration).

# Steps
- Download the Integration

Download the parcel_tracking_info integration files.
Place the parcel_tracking_info directory in your Home Assistant's custom_components directory:

```
custom_components/
└── parcel_tracking_info/
    ├── __init__.py
    ├── manifest.json
    ├── config_flow.py
    ├── parcel_tracking.py
    ├── carrier_apis.py
    ├── sensor.py
    ├── trackingstatus.py
    └── (other files)

```

- Restart Home Assistant to load the new integration.

# Configuration
## Adding the Integration

### Navigate to Integrations
- In Home Assistant, go to Settings > Devices & Services.

### Add Integration
- Click on Add Integration.
- Search for Parcel Tracking Info and select it.

### Carrier Selection
- Configure Carrier: Choose this option to set up a carrier.
- Carrier Template: Select a carrier template (e.g., DHL, GLS, Hermes, DPD) or custom to define your own.

### Custom Carrier (if applicable)
- If you selected custom, you'll be prompted to enter a unique carrier name and display name.

### Email Configuration
Provide your email server settings:
- IMAP Server: e.g., imap.gmail.com
- IMAP Port: e.g., 993
- Email Account: Your email address.
- Email Password: Password or app-specific password.
- Email Folder: Folder to search for emails (default is inbox).
- Update Interval: Frequency (in minutes) to check for new emails.
- Email Age: How many days back to search for emails.

### Carrier Configuration
- Carrier Name: Enter the name of the carrier (e.g., dhl, dhl_custom).
- Display Name: Friendly name for the integration.
- Search Criteria: IMAP search criteria to find relevant emails.
- Tracking Pattern: Regex pattern to extract tracking numbers.
- ETA String: Keyword or phrase indicating estimated delivery date in emails.
- ETA Date Pattern: Regex pattern to extract the date.
- Status Strings: Comma-separated list of keywords to identify shipment status.
- Tracking Link URL: URL template for tracking links.
- API URL: Carrier API endpoint (if applicable).
- API Key: Your API key for the carrier (if applicable).

### Test Parsing (Optional)
- Provide a sample email body to test your parsing rules.
- Review the test results to ensure tracking information is correctly extracted.

### API Configuration (if applicable)
- If the carrier requires API integration, you'll be prompted to enter the API URL and API Key.

### Finalize Setup
- Review your settings and click Finish to complete the setup.

# Usage
### Sensors
After configuring the integration, several sensors will be created:
- Parcel Tracking Status: Indicates the current status of the shipment (e.g., in_transit, delivered).
- Parcel Tracking ETA: Shows the estimated delivery date.
- Parcel Tracking Number: Displays the tracking number.
- Parcel Tracking Link: Provides a URL to track the shipment on the carrier's website.

## Viewing Shipment Information
- Navigate to Overview in Home Assistant.
- Add the sensors to your dashboard to monitor your shipments.

## Notifications
- Configure automations to send notifications based on sensor updates.
- Example: Notify when a package status changes to out_for_delivery.

# Options and Customization
## Editing Carrier Info

- Navigate to Integrations: Go to Settings > Devices & Services.
- Select the Integration
- Find Parcel Tracking Info and click Configure.
- Edit Options: Choose Edit Carrier Info to change the carrier name and display name.

## Updating Email Settings
- In the options flow, select Email Configuration to update your email account settings.

## Modifying Carrier Parsing Rules
- Choose Carrier Configuration in the options flow to adjust parsing rules, regex patterns, and status strings.

## API Settings
- Update API URLs and keys by selecting API Configuration in the options flow.

# Advanced Configuration
## Custom Carriers
- When selecting custom as your carrier, you can define all parsing rules and API settings manually.
- This is useful for carriers not included in the predefined templates.
-
## Carrier API Implementations
- The integration supports API calls to fetch tracking information.
- API implementations are modularized in the carrier_apis.py file.

### Supported Carriers with APIs:
- DHL: Implemented in DHLAPI class.
- GLS, Hermes, DPD: Placeholders provided; implement as needed.

## Adding New Carriers
To add a new carrier API:
- Create a new class in carrier_apis.py inheriting from BaseCarrierAPI.
- Implement the fetch_tracking_info method with carrier-specific logic.
- Update CARRIER_API_CLASSES with the new carrier key and class.

## Troubleshooting
### Cannot Connect to Email Server
Error: Cannot connect to host your_imap_server:port
Solution:
- Verify IMAP server and port are correct.
- Check your email credentials.
- Ensure that IMAP access is enabled in your email account settings.
- For Gmail, consider using an app-specific password.

### API Connection Issues
Error: Client error while fetching tracking info
Solution:
- Confirm that the API URL is correct and includes https://.
- Ensure your API key is valid.
- Check network connectivity and firewall settings.

### Parsing Errors
Issue: Tracking information is not extracted correctly.
Solution:
- Review and adjust your regex patterns for tracking_pattern, eta_date_pattern.
- Test your parsing rules using the Test Parsing step in the configuration flow.
- Ensure that status_strings include all relevant keywords.

### No API Implementation Found
Error: No API implementation found for carrier 'your_carrier'
Solution:
- Ensure that the carrier name matches a key in CARRIER_API_CLASSES.
- Carrier names are case-insensitive but should be normalized (lowercase, no spaces).
- If using a custom carrier, API integration may not be available.

### Status Normalization
Issue: Status codes from the API are not normalized.
Solution:
- The integration uses the map_status function to normalize status descriptions.
- Ensure that map_status includes mappings for all possible status descriptions from the API.
- Update trackingstatus.py to handle new status codes as needed.

## Frequently Asked Questions
### Can I Track Multiple Shipments from Different Carriers?
- Yes, you can set up multiple instances of the integration, each configured for a different carrier.
### How Do I Handle Carriers Not Listed in the Templates?
- Choose custom during the carrier selection step.
- Define all necessary parsing rules and API settings manually.
### How Often Does the Integration Check for Updates?
- The Update Interval setting determines how frequently the integration checks for new emails.
- Default is every 60 minutes; adjust as needed.
### Can I Export and Import Configuration?
- The integration supports exporting configuration through the options flow.
- Import functionality may be disabled or unavailable in certain versions.

## Developer Notes
### Code Structure
- config_flow.py: Handles the configuration flow and user interactions.
- carrier_apis.py: Contains carrier-specific API implementations.
- parcel_tracking.py: Core logic for fetching and processing emails.
- sensor.py: Defines the sensors exposed by the integration.
- trackingstatus.py: Contains the map_status function for status normalization.

### Extensibility
- The integration is designed to be modular and extensible.
- Adding support for new carriers involves minimal changes:
- Implement a new API class in carrier_apis.py.
- Update parsing rules and templates as needed.

### Conclusion
The Parcel Tracking Info integration brings parcel tracking directly into your smart home, keeping you informed about your shipments' statuses without leaving Home Assistant. With flexible configuration options and support for multiple carriers, you can tailor the integration to meet your specific needs.

## Support
If you encounter any issues or have suggestions for improvement, please reach out to me.

Happy tracking!


