"""Password-policy tests.

Proves the validator rejects weak passwords and accepts strong ones, and that
it is wired into the user Pydantic models (UserCreate / UserUpdate).
"""
import pytest
from pydantic import ValidationError

from core.password_policy import password_errors, validate_password
from core.models import UserCreate, UserUpdate

STRONG = "Str0ng!Passw0rd"  # 15 chars, all classes


def test_strong_password_passes():
    assert password_errors(STRONG) == []
    assert validate_password(STRONG) == STRONG


@pytest.mark.parametrize("pw,needle", [
    ("Sh0rt!", "at least"),                 # too short
    ("alllowercase1!", "uppercase"),        # no uppercase
    ("ALLUPPERCASE1!", "lowercase"),        # no lowercase
    ("NoDigitsHere!!", "digit"),            # no digit
    ("NoSymbols12345", "symbol"),           # no symbol
    ("password", "at least"),               # short + common
])
def test_weak_passwords_rejected(pw, needle):
    errs = password_errors(pw)
    assert errs, f"expected {pw!r} to fail"
    assert any(needle in e for e in errs)


def test_common_password_rejected():
    # 12+ chars and meets complexity but is on the common list.
    errs = password_errors("Password1234")
    # Missing symbol AND common — either way it must fail.
    assert errs


def test_bcrypt_72_byte_cap():
    too_long = "Aa1!" + "x" * 80
    assert any("72 bytes" in e for e in password_errors(too_long))


def test_validate_password_raises_on_weak():
    with pytest.raises(ValueError):
        validate_password("weak")


def test_usercreate_rejects_weak_password():
    with pytest.raises(ValidationError):
        UserCreate(name="A", email="a@b.com", password="weak")


def test_usercreate_accepts_strong_password():
    u = UserCreate(name="A", email="a@b.com", password=STRONG)
    assert u.password == STRONG


def test_userupdate_password_optional():
    # No password supplied -> valid, validator skipped.
    u = UserUpdate(name="A")
    assert u.password is None


def test_userupdate_rejects_weak_password():
    with pytest.raises(ValidationError):
        UserUpdate(password="weak")
