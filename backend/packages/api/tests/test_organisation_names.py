from codecraft_api.organisation_names import personal_organisation_name


def test_personal_organisation_name_is_the_default() -> None:
    assert personal_organisation_name() == "My organisation"
