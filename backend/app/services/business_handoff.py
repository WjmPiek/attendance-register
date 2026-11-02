"""Fill missing holder business fields from the authenticated main-system handoff."""
from fastapi import HTTPException

PROFILE_LIMITS = {
    'franchise_name': 255, 'business_name': 255, 'trading_as': 255,
    'business_registration_number': 100, 'vat_number': 100, 'office_address': 10000,
    'website': 500, 'office_number': 50, 'twenty_four_hour_number': 50, 'contact_number': 50,
}


def fill_business_profile(profile, handoff):
    details = handoff.get('business_profile')
    if not details:
        return
    primary = handoff.get('primary_franchise_id')
    scope = handoff.get('branch_scope') or []
    if not isinstance(details, dict) or not primary or details.get('franchise_id') != primary or not any(b.get('id') == primary for b in scope):
        raise HTTPException(400, 'Business profile must belong to the approved primary franchise.')
    branch_names = {str(b.get('name') or '').strip() for b in scope}
    for key, limit in PROFILE_LIMITS.items():
        incoming = str(details.get(key) or '').strip()
        existing = str(getattr(profile, key, None) or '').strip()
        # Earlier SSO versions copied the branch label into the registered name.
        placeholder = key in {'business_name', 'franchise_name'} and existing in branch_names
        if incoming and len(incoming) <= limit and (not existing or placeholder):
            setattr(profile, key, incoming)
