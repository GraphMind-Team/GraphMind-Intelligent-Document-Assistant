from app.auth.service import hash_password


def test_hash_password_round_trips():
    from passlib.hash import bcrypt_sha256

    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert bcrypt_sha256.verify("correct horse battery staple", hashed)


def test_hash_password_never_plaintext():
    hashed = hash_password("s3cret!")
    assert "s3cret!" not in hashed
    assert hashed.startswith("$bcrypt-sha256$")


def test_hash_password_handles_long_password():
    # bcrypt alone truncates at 72 bytes; bcrypt_sha256 exists specifically
    # so a long password isn't silently truncated before hashing.
    from passlib.hash import bcrypt_sha256

    long_password = "x" * 200
    hashed = hash_password(long_password)
    assert bcrypt_sha256.verify(long_password, hashed)
    assert not bcrypt_sha256.verify("x" * 199, hashed)
