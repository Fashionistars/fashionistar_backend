"""
Static reference data and validators for Fashionistar forms.

The frontend bundles this same data for speed. The backend keeps an
independent copy here because all submitted country, location, and bank
values must be validated before they are persisted.
"""

from apps.common.reference_data.banks import (  # noqa: F401
    get_bank,
    get_banks,
    is_valid_bank_code,
)
from apps.common.reference_data.countries import (  # noqa: F401
    get_countries,
    get_country,
    is_valid_country_code,
)
from apps.common.reference_data.locations import (  # noqa: F401
    get_cities,
    get_lgas,
    get_states,
    is_valid_city_code,
    is_valid_lga_code,
    is_valid_state_code,
)
from apps.common.reference_data.validators import (  # noqa: F401
    validate_bank_code,
    validate_city_or_custom_city,
    validate_country_code,
    validate_lga_code,
    validate_state_code,
    validate_street_address,
)

