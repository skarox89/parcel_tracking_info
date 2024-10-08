# custom_components/parcel_tracking_info/config_flow.py

import json
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_HOST, CONF_PORT
from homeassistant.helpers import config_validation as cv
from homeassistant.components.persistent_notification import create as persistent_notification_create
from .const import DOMAIN
from .carriers import CARRIER_TEMPLATES, add_custom_carrier
from .parcel_tracking import extract_tracking_number, extract_eta_from_email, extract_status_from_email

_LOGGER = logging.getLogger(__name__)


class ParcelTrackingInfoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Parcel Tracking Info."""

    VERSION = 3  # Incremented version for schema changes

    def __init__(self):
        self.template = {}
        self.user_input = {}
        self.carrier = ''
        self.api_required = False

    async def async_step_user(self, user_input=None):
        """Step 1: Carrier selection or import configuration."""
        errors = {}
        if user_input is not None:
            action = user_input.get('action')
            if action == 'configure_carrier':
                self.carrier = user_input.get('carrier', 'custom')
                self.user_input['carrier'] = self.carrier.lower().strip()  # Store carrier
                self.template = CARRIER_TEMPLATES.get(self.carrier, {})
                self.api_required = bool(self.template.get('api_url'))

                if self.carrier == 'custom':
                    return await self.async_step_custom_carrier()
                else:
                    return await self.async_step_email_config()
            # elif action == 'import_config':
            #    return await self.async_step_import_config()
            else:
                errors['base'] = 'invalid_action'

        # Prepare the selection schema with carriers including 'custom'
        selection_schema = vol.Schema({
            vol.Required('action', default='configure_carrier'): vol.In({
                'configure_carrier': "Configure Carrier",
                # 'import_config': "Import Configuration",
            }),
            vol.Optional('carrier', default='dhl'): vol.In(list(CARRIER_TEMPLATES.keys()) + ['custom']),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=selection_schema,
            errors=errors,
        )

    async def async_step_import_config(self, user_input=None):
        """Step to import configuration."""
        errors = {}
        if user_input is not None:
            try:
                # Attempt to parse the imported configuration
                imported_config = json.loads(user_input.get('imported_config', '{}'))
                self.user_input.update(imported_config)
                self.carrier = self.user_input.get('carrier', 'custom')
                self.api_required = bool(self.user_input.get('api_url'))
                return await self.async_step_email_config()
            except json.JSONDecodeError:
                errors['base'] = 'invalid_import'
            except Exception as e:
                _LOGGER.error(f"Unexpected error during import_config: {e}")
                errors['base'] = 'unknown_error'

        import_schema = vol.Schema({
            vol.Required('imported_config'): cv.string,
        })

        return self.async_show_form(
            step_id="import_config",
            data_schema=import_schema,
            errors=errors,
        )

    async def async_step_email_config(self, user_input=None):
        """Step 2: Email configuration."""
        errors = {}
        if user_input is not None:
            try:
                # Test email connection
                imap_server = user_input.get(CONF_HOST)
                imap_port = user_input.get(CONF_PORT)
                email_account = user_input.get(CONF_EMAIL)
                email_password = user_input.get(CONF_PASSWORD)

                connected, error_code = await self.hass.async_add_executor_job(
                    test_email_connection, imap_server, imap_port, email_account, email_password
                )

                if not connected:
                    errors['base'] = error_code or 'cannot_connect'
                else:
                    # Store email config and proceed to carrier config
                    self.user_input.update(user_input)
                    return await self.async_step_carrier_config()
            except Exception as e:
                _LOGGER.error(f"Error in async_step_email_config: {e}")
                errors['base'] = 'unknown_error'

        # Prepare the email configuration schema
        email_schema = vol.Schema({
            vol.Required(CONF_HOST, default=self.template.get(CONF_HOST, "imap.gmail.com")): cv.string,
            vol.Required(CONF_PORT, default=self.template.get(CONF_PORT, 993)): cv.port,
            vol.Required(CONF_EMAIL, default=self.template.get(CONF_EMAIL, "")): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
            vol.Required('email_folder', default=self.template.get('email_folder', "inbox")): cv.string,
            vol.Optional('update_interval', default=60): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional('email_age', default=10): vol.All(vol.Coerce(int), vol.Range(min=1)),
        })

        return self.async_show_form(
            step_id="email_config",
            data_schema=email_schema,
            errors=errors,
        )

    async def async_step_carrier_config(self, user_input=None):
        """Step 3: Carrier configuration (regex patterns, email parsing rules)."""
        errors = {}
        if user_input is not None:
            try:
                # Update carrier and display_name
                self.carrier = user_input.get('carrier', self.carrier)
                self.user_input['carrier'] = self.carrier.lower().strip()
                self.user_input['display_name'] = user_input.get('display_name', self.carrier.capitalize())

                # Update user_input with the rest of the data
                self.user_input.update(user_input)

                # Determine if API configuration is required based on user input
                self.api_required = bool(user_input.get('api_url'))

                # Proceed to test parsing step
                return await self.async_step_test_parsing()
            except Exception as e:
                _LOGGER.error(f"Error in async_step_carrier_config: {e}")
                errors['base'] = 'unknown_error'

        try:
            # Prepare the carrier configuration schema
            carrier_schema = vol.Schema({
                vol.Required('carrier', default=self.carrier): cv.string,
                vol.Required('display_name', default=self.carrier.capitalize()): cv.string,
                vol.Required('search_criteria', default=self.template.get('search_criteria', f'(FROM "{self.carrier}")')): cv.string,
                vol.Required('tracking_pattern', default=self.template.get('tracking_pattern', r"")): cv.string,
                vol.Optional('eta_string', default=self.template.get('email_parsing', {}).get('eta_string', '')): cv.string,
                vol.Optional('eta_date_pattern', default=self.template.get('email_parsing', {}).get('eta_date_pattern', '')): cv.string,
                vol.Optional('status_strings', default=','.join(self.template.get('email_parsing', {}).get('status_strings', []))): cv.string,
                vol.Optional('tracking_link_url', default=self.template.get('tracking_link_url', '')): cv.string,
                vol.Optional('api_url', default=self.template.get('api_url', '')): cv.string,
                vol.Optional('api_key', default=self.template.get('api_key', '')): cv.string,
            })

            return self.async_show_form(
                step_id="carrier_config",
                data_schema=carrier_schema,
                errors=errors,
            )
        except Exception as e:
            _LOGGER.error(f"Error preparing carrier_config form: {e}")
            errors['base'] = 'unknown_error'
            return self.async_show_form(
                step_id="carrier_config",
                data_schema=vol.Schema({}),
                errors=errors,
            )

    async def async_step_custom_carrier(self, user_input=None):
        """Step to input a custom carrier and display name."""
        errors = {}
        if user_input is not None:
            custom_carrier = user_input.get('custom_carrier', '').strip()
            display_name = user_input.get('display_name', '').strip()
            if not custom_carrier:
                errors['custom_carrier'] = 'invalid_name'
            elif not display_name:
                errors['display_name'] = 'invalid_display_name'
            else:
                try:
                    # Store carrier and display name
                    self.carrier = custom_carrier
                    self.user_input['carrier'] = self.carrier.lower().strip()
                    self.user_input['display_name'] = display_name

                    # Optionally, add to CARRIER_TEMPLATES or handle as needed
                    add_custom_carrier(
                        name=custom_carrier,
                        api_url=self.user_input.get('api_url', ''),
                        search_criteria=self.user_input.get('search_criteria', f'(FROM "{custom_carrier}")'),
                        tracking_pattern=self.user_input.get('tracking_pattern', r""),
                        email_parsing=self.user_input.get('email_parsing', {})
                    )

                    return await self.async_step_email_config()
                except Exception as e:
                    _LOGGER.error(f"Error in async_step_custom_carrier: {e}")
                    errors['base'] = 'unknown_error'

        # Define the schema with both custom_carrier and display_name
        custom_carrier_schema = vol.Schema({
            vol.Required('custom_carrier'): cv.string,
            vol.Required('display_name'): cv.string,
        })

        return self.async_show_form(
            step_id="custom_carrier",
            data_schema=custom_carrier_schema,
            errors=errors,
            description_placeholders={
                'info': 'Please enter a unique name and a display name for your custom carrier.'
            },
        )

    async def async_step_test_parsing(self, user_input=None):
        """Step 4: Test parsing rules with sample email content."""
        errors = {}
        if user_input is not None:
            try:
                email_body = user_input.get('sample_email', '')
                if email_body:
                    # Extract the parsing rules from previous steps
                    tracking_pattern = self.user_input.get('tracking_pattern', '')
                    eta_string = self.user_input.get('eta_string', '')
                    eta_date_pattern = self.user_input.get('eta_date_pattern', '')
                    status_strings = [s.strip() for s in self.user_input.get('status_strings', '').split(',') if s.strip()]

                    # Test tracking number extraction
                    tracking_number = extract_tracking_number(email_body, tracking_pattern, set())
                    if not tracking_number:
                        errors['base'] = 'no_tracking_number_found'

                    # Test ETA extraction
                    eta = ''
                    if eta_string and eta_date_pattern:
                        eta = await extract_eta_from_email(self.hass, email_body, eta_string, eta_date_pattern)
                        if not eta:
                            errors['eta'] = 'no_eta_found'

                    # Test status extraction
                    status = ''
                    if status_strings:
                        status = extract_status_from_email(email_body, status_strings)
                        if not status:
                            errors['status'] = 'no_status_found'

                    if not errors:
                        # Display results and proceed to next step
                        persistent_notification_create(
                            hass=self.hass,
                            message=f"**Test Parsing Results:**\n\n"
                                    f"**Tracking Number:** {tracking_number}\n"
                                    f"**ETA:** {eta or 'Not found'}\n"
                                    f"**Status:** {status or 'Not found'}",
                            title="Parcel Tracking Info - Parsing Test"
                        )
                # Proceed to create entry if API config is already provided
                if self.api_required and ('api_key' not in self.user_input or 'api_url' not in self.user_input):
                    return await self.async_step_api_config()
                else:
                    return await self._create_entry()
            except Exception as e:
                _LOGGER.error(f"Error in async_step_test_parsing: {e}")
                errors['base'] = 'unknown_error'

        # Prepare the test parsing schema
        test_parsing_schema = vol.Schema({
            vol.Optional('sample_email'): cv.string,
        })

        return self.async_show_form(
            step_id="test_parsing",
            data_schema=test_parsing_schema,
            errors=errors,
            description_placeholders={
                'note': 'You can enter a sample email body to test your parsing rules (optional). Large inputs are supported.'
            },
        )

    async def async_step_api_config(self, user_input=None):
        """Step 5: API configuration."""
        # Skip this step if API info is already collected
        if 'api_key' in self.user_input and 'api_url' in self.user_input:
            return await self._create_entry()
    
        errors = {}
        if user_input is not None:
            try:
                self.user_input.update(user_input)
                return await self._create_entry()
            except Exception as e:
                _LOGGER.error(f"Error in async_step_api_config: {e}")
                errors['base'] = 'unknown_error'
    
        # Define API configuration schema based on selected carrier
        carrier = self.user_input.get('carrier')
        api_schema = vol.Schema({})
    
        if carrier == 'dhl':
            api_schema = vol.Schema({
                vol.Required('api_key'): cv.string,
                vol.Required('api_url', default='https://api-eu.dhl.com/track/shipments'): cv.url,
            })
        elif carrier == 'gls':
            api_schema = vol.Schema({
                vol.Required('api_key'): cv.string,
                vol.Required('api_url', default='https://api.gls.com/track/shipments'): cv.url,
            })
        # Add other carriers as needed
    
        return self.async_show_form(
            step_id="api_config",
            data_schema=api_schema,
            errors=errors,
        )

    async def async_step_export_config(self, user_input=None):
        """Step to export existing configuration."""
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="", data=None)
        try:
            current_options = {**self.user_input, **self.user_input.get('options', {})}
            exported_config = json.dumps(current_options, indent=2)

            # Inform the user that the configuration has been exported
            persistent_notification_create(
                hass=self.hass,
                message=f"**Exported Configuration:**\n\n```json\n{exported_config}\n```",
                title="Parcel Tracking Info - Export Configuration"
            )

            return self.async_show_form(
                step_id="export_config",
                data_schema=vol.Schema({}),
                description_placeholders={
                    'message': "Your configuration has been exported and can be found in the Home Assistant notifications."
                },
            )
        except Exception as e:
            _LOGGER.error(f"Error exporting configuration: {e}")
            errors['base'] = 'export_failed'
            return self.async_show_form(
                step_id="export_config",
                data_schema=vol.Schema({}),
                errors=errors,
            )

    async def _create_entry(self):
        """Create the config entry."""
        try:
            # Generate a unique ID based on the email account and carrier
            email = self.user_input.get(CONF_EMAIL, '').lower()

            unique_id = f"{email}_{self.carrier}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # Process status_strings into a list
            status_strings = self.user_input.get('status_strings', '')
            if isinstance(status_strings, str):
                status_strings = [s.strip() for s in status_strings.split(',') if s.strip()]
                self.user_input['status_strings'] = status_strings
            elif isinstance(status_strings, list):
                self.user_input['status_strings'] = [s.strip() for s in status_strings if s.strip()]
            else:
                self.user_input['status_strings'] = []

            # Set display_name
            display_name = self.user_input.get('display_name', self.carrier.capitalize())

            # Create the entry with display_name as the title
            return self.async_create_entry(title=display_name, data=self.user_input)
        except Exception as e:
            _LOGGER.error(f"Error creating config entry: {e}")
            raise

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for the integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Step 1: Decide which options to configure."""
        return await self.async_step_choose_options()

    async def async_step_choose_options(self, user_input=None):
        """Step to choose which options to configure."""
        if user_input is not None:
            option = user_input.get('option')
            if option == 'email_config':
                return await self.async_step_email_config()
            elif option == 'carrier_config':
                return await self.async_step_carrier_config()
            elif option == 'api_config':
                return await self.async_step_api_config()
            elif option == 'export_config':
                return await self.async_step_export_config()
            elif option == 'edit_carrier_info':
                return await self.async_step_edit_carrier_info()
            else:
                return self.async_abort(reason='invalid_option')

        options_schema = vol.Schema({
            vol.Required('option'): vol.In({
                'email_config': "Email Configuration",
                'carrier_config': "Carrier Configuration",
                'edit_carrier_info': "Edit Carrier Info",
                'api_config': "API Configuration",
                'export_config': "Export Configuration",
            })
        })

        return self.async_show_form(
            step_id='choose_options',
            data_schema=options_schema
        )

    async def async_step_edit_carrier_info(self, user_input=None):
        """Step to edit the carrier and display name."""
        errors = {}
        if user_input is not None:
            new_carrier = user_input.get('carrier', '').strip()
            new_display_name = user_input.get('display_name', '').strip()
            if not new_carrier:
                errors['carrier'] = 'invalid_carrier'
            elif not new_display_name:
                errors['display_name'] = 'invalid_display_name'
            else:
                try:
                    # Update the config entry's data with new carrier and display_name
                    updated_data = {**self.config_entry.data}
                    updated_data['carrier'] = new_carrier
                    updated_data['display_name'] = new_display_name

                    # Update the config entry
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        title=new_display_name,
                        data=updated_data
                    )
                    return self.async_create_entry(title="", data=None)
                except Exception as e:
                    _LOGGER.error(f"Error in async_step_edit_carrier_info: {e}")
                    errors['base'] = 'unknown_error'

        # Pre-fill the form with the current carrier and display_name
        existing_carrier = self.config_entry.data.get('carrier', '')
        existing_display_name = self.config_entry.data.get('display_name', self.config_entry.title)

        carrier_info_schema = vol.Schema({
            vol.Required('carrier', default=existing_carrier): cv.string,
            vol.Required('display_name', default=existing_display_name): cv.string,
        })

        return self.async_show_form(
            step_id="edit_carrier_info",
            data_schema=carrier_info_schema,
            errors=errors,
            description_placeholders={
                'info': 'You can edit the carrier and display name for your integration.'
            },
        )

    async def async_step_email_config(self, user_input=None):
        """Email configuration in options flow."""
        errors = {}
        if user_input is not None:
            try:
                # Test email connection
                imap_server = user_input.get(CONF_HOST)
                imap_port = user_input.get(CONF_PORT)
                email_account = user_input.get(CONF_EMAIL)
                email_password = user_input.get(CONF_PASSWORD)

                connected, error_code = await self.hass.async_add_executor_job(
                    test_email_connection, imap_server, imap_port, email_account, email_password
                )

                if not connected:
                    errors['base'] = error_code or 'cannot_connect'
                else:
                    # Update the config entry options with the new email config
                    updated_options = {**self.config_entry.options, **user_input}
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, options=updated_options
                    )
                    return self.async_create_entry(title="", data=None)
            except Exception as e:
                _LOGGER.error(f"Error in OptionsFlowHandler.async_step_email_config: {e}")
                errors['base'] = 'unknown_error'

        # Use the existing config entry options to pre-fill the form
        existing_options = self.config_entry.options
        existing_data = self.config_entry.data

        email_schema = vol.Schema({
            vol.Required(CONF_HOST, default=existing_options.get(CONF_HOST, existing_data.get(CONF_HOST, "imap.gmail.com"))): cv.string,
            vol.Required(CONF_PORT, default=existing_options.get(CONF_PORT, existing_data.get(CONF_PORT, 993))): cv.port,
            vol.Required(CONF_EMAIL, default=existing_options.get(CONF_EMAIL, existing_data.get(CONF_EMAIL, ""))): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
            vol.Required('email_folder', default=existing_options.get('email_folder', existing_data.get('email_folder', "inbox"))): cv.string,
            vol.Optional('update_interval', default=existing_options.get('update_interval', existing_data.get('update_interval', 60))): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional('email_age', default=existing_options.get('email_age', existing_data.get('email_age', 10))): vol.All(vol.Coerce(int), vol.Range(min=1)),
        })

        return self.async_show_form(
            step_id="email_config",
            data_schema=email_schema,
            errors=errors,
        )

    async def async_step_carrier_config(self, user_input=None):
        """Carrier configuration in options flow."""
        errors = {}
        if user_input is not None:
            try:
                # Process status_strings into a list
                status_strings = user_input.get('status_strings', '')
                if isinstance(status_strings, str):
                    status_strings = [s.strip() for s in status_strings.split(',') if s.strip()]
                elif isinstance(status_strings, list):
                    status_strings = [s.strip() for s in status_strings if s.strip()]
                else:
                    status_strings = []
                user_input['status_strings'] = status_strings

                # Update the config entry options with the new carrier config
                updated_options = {**self.config_entry.options, **user_input}
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=updated_options
                )
                return self.async_create_entry(title="", data=None)
            except Exception as e:
                _LOGGER.error(f"Error in OptionsFlowHandler.async_step_carrier_config: {e}")
                errors['base'] = 'unknown_error'

        existing_options = self.config_entry.options
        existing_data = self.config_entry.data

        carrier_schema = vol.Schema({
            vol.Required('search_criteria', default=existing_options.get('search_criteria', existing_data.get('search_criteria', ''))): cv.string,
            vol.Required('tracking_pattern', default=existing_options.get('tracking_pattern', existing_data.get('tracking_pattern', ''))): cv.string,
            vol.Optional('eta_string', default=existing_options.get('eta_string', existing_data.get('eta_string', ''))): cv.string,
            vol.Optional('eta_date_pattern', default=existing_options.get('eta_date_pattern', existing_data.get('eta_date_pattern', ''))): cv.string,
            vol.Optional('status_strings', default=','.join(existing_options.get('status_strings', existing_data.get('status_strings', [])))): cv.string,
            vol.Optional('tracking_link_url', default=existing_options.get('tracking_link_url', existing_data.get('tracking_link_url', ''))): cv.string,
        })

        return self.async_show_form(
            step_id="carrier_config",
            data_schema=carrier_schema,
            errors=errors,
        )

    async def async_step_api_config(self, user_input=None):
        """API configuration in options flow."""
        errors = {}
        if user_input is not None:
            try:
                # Update the config entry options with the new API config
                updated_options = {**self.config_entry.options, **user_input}
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=updated_options
                )
                return self.async_create_entry(title="", data=None)
            except Exception as e:
                _LOGGER.error(f"Error in OptionsFlowHandler.async_step_api_config: {e}")
                errors['base'] = 'unknown_error'

        existing_options = self.config_entry.options
        existing_data = self.config_entry.data

        api_schema = vol.Schema({
            vol.Required('api_key', default=existing_options.get('api_key', existing_data.get('api_key', ''))): cv.string,
            vol.Required('api_url', default=existing_options.get('api_url', existing_data.get('api_url', ''))): cv.string,
        })

        return self.async_show_form(
            step_id="api_config",
            data_schema=api_schema,
            errors=errors,
        )

    async def async_step_export_config(self, user_input=None):
        """Step to export existing configuration."""
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="", data=None)
        try:
            current_options = {**self.config_entry.data, **self.config_entry.options}
            exported_config = json.dumps(current_options, indent=2)

            # Inform the user that the configuration has been exported
            persistent_notification_create(
                hass=self.hass,
                message=f"**Exported Configuration:**\n\n```json\n{exported_config}\n```",
                title="Parcel Tracking Info - Export Configuration"
            )

            return self.async_show_form(
                step_id="export_config",
                data_schema=vol.Schema({}),
                description_placeholders={
                    'message': "Your configuration has been exported and can be found in the Home Assistant notifications."
                },
            )
        except Exception as e:
            _LOGGER.error(f"Error exporting configuration: {e}")
            errors['base'] = 'export_failed'
            return self.async_show_form(
                step_id="export_config",
                data_schema=vol.Schema({}),
                errors=errors,
            )


def test_email_connection(imap_server, imap_port, email_account, email_password):
    """Test email connection."""
    import imaplib
    try:
        with imaplib.IMAP4_SSL(imap_server, imap_port) as mail:
            mail.login(email_account, email_password)
        return True, ""
    except imaplib.IMAP4.error as e:
        return False, str(e)
    except Exception as e:
        _LOGGER.error(f"Unexpected error in test_email_connection: {e}")
        return False, "unknown_error"
