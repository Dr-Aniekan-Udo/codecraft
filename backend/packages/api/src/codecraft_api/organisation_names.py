"""The personal-organisation naming rule.

This rule applies only when a personal organisation is created. It is never
reapplied afterwards. The default is deliberately generic because the owner can
rename the organisation later.
"""


def personal_organisation_name() -> str:
    return "My organisation"
