import pytest

from champs.random_champs.filters import RoleFilter


def test_role_filter_sanitise_filter_maps_aliases() -> None:
    assert RoleFilter.sanitise_filter("adc") == "BOT"
    assert RoleFilter.sanitise_filter("jgl") == "JUNGLE"
    assert RoleFilter.sanitise_filter("support") == "SUPP"


def test_role_filter_sanitise_filter_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        RoleFilter.sanitise_filter("invalid-role")
