# custom_components/parcel_tracking_info/options_flow.py

import json
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_HOST, CONF_PORT
from homeassistant.helpers import config_validation as cv
from homeassistant.components.persistent_notification import create as persistent_notification_create
from .const import DOMAIN
from .carrier_apis import CARRIER_API_CLASSES
from .helpers import test_email_connection, process_status_strings

_LOGGER = logging.getLogger(__name__)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for the integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.user_input = {}  # Initialize user_input
        self.api_required = False  # Initialize api_required

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
            elif option == 'export_config':
                return await self.async_step_export_config()
            elif option == 'edit_carrier_info':
                return await self.async_step_edit_carrier_info()
            elif option == 'edit_api_template':
                return await self.async_step_edit_api_template()
            else:
                return self.async_abort(reason='invalid_option')

        options_schema = vol.Schema({
            vol.Required('option'): vol.In({
                'email_config': "Edit Email Configuration",
                'carrier_config': "Edit Carrier Configuration",
                'edit_carrier_info': "Edit Carrier Name",
                'edit_api_template': "Edit API Configuration / Template",
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
                    updated_data['carrier'] = new_carrier.lower()
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

    async def async_step_edit_api_template(self, user_input=None):
        """Step to edit the API template."""
        errors = {}
        if user_input is not None:
            new_api_template = user_input.get('api_template')
            if not new_api_template:
                errors['api_template'] = 'invalid_selection'
            else:
                try:
                    # Update the config entry's data with the new API template
                    updated_data = {**self.config_entry.data}
                    updated_data['api_template'] = new_api_template
                    # Update api_required flag
                    updated_data['api_required'] = new_api_template != 'no_api'

                    # Update the config entry
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=updated_data
                    )
                    return self.async_create_entry(title="", data=None)
                except Exception as e:
                    _LOGGER.error(f"Error in async_step_edit_api_template: {e}")
                    errors['base'] = 'unknown_error'

        # Prepare the list of API templates
        api_templates = list(CARRIER_API_CLASSES.keys()) + ['no_api']

        # Prepare the selection schema
        api_template_schema = vol.Schema({
            vol.Required('api_template', default=self.config_entry.data.get('api_template', 'no_api')): vol.In(api_templates),
        })

        return self.async_show_form(
            step_id="edit_api_template",
            data_schema=api_template_schema,
            errors=errors,
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

                # Store the user_input temporarily
                self.user_input = user_input

                # Proceed to the next step to select the API template
                return await self.async_step_api_config()
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
        if not self.api_required:
            # Update the config entry options with the collected data
            updated_options = {**self.config_entry.options, **self.user_input}
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=updated_options
            )
            return self.async_create_entry(title="", data=None)
        errors = {}
        if user_input is not None:
            try:
                # Update the config entry options with the new API config
                updated_options = {**self.config_entry.options, **self.user_input, **user_input}
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=updated_options
                )
                return self.async_create_entry(title="", data=None)
            except Exception as e:
                _LOGGER.error(f"Error in OptionsFlowHandler.async_step_api_config: {e}")
                errors['base'] = 'unknown_error'

        carrier = self.config_entry.data.get('carrier')
        api_schema = vol.Schema({})

        if self.config_entry.data.get('api_template') in CARRIER_API_CLASSES:
            default_api_url = CARRIER_API_CLASSES[self.config_entry.data.get('api_template')].get('api_url', '')
            api_schema = vol.Schema({
                vol.Required('api_key', default=self.config_entry.options.get('api_key', '')): cv.string,
                vol.Required('api_url', default=self.config_entry.options.get('api_url', default_api_url)): cv.string,
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
