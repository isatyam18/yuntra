from __future__ import annotations

from yuntra.security import redact_payload, redact_text, sensitive_markers


def test_redact_quoted_credentials_with_spaces():
    # Quoted values containing spaces must be fully redacted, not partially leaked
    text1 = 'password: "hunter two"'
    redacted1 = redact_text(text1)
    assert "hunter" not in redacted1
    assert "two" not in redacted1
    assert "password=[REDACTED]" in redacted1

    text2 = "api_key = 'sk-abc 123'"
    redacted2 = redact_text(text2)
    assert "sk-abc" not in redacted2
    assert "123" not in redacted2
    assert "api_key=[REDACTED]" in redacted2


def test_redact_authorization_bearer():
    text = "Authorization: Bearer my-secret-token-xyz"
    redacted = redact_text(text)
    assert "my-secret-token-xyz" not in redacted
    assert "Authorization=[REDACTED]" in redacted


def test_redact_raw_tokens_without_key_prefix():
    # GitHub PAT
    gh_token = "ghp_123456789012345678901234567890123456"
    assert "1234567890" not in redact_text(f"Token is {gh_token}")
    assert "[GITHUB_TOKEN_REDACTED]" in redact_text(f"Token is {gh_token}")

    # AWS Key ID
    aws_key = "AKIAIOSFODNN7EXAMPLE"
    assert "IOSFODNN7" not in redact_text(f"Access key: {aws_key}")
    assert "[AWS_ACCESS_KEY_REDACTED]" in redact_text(f"Access key: {aws_key}")

    # API key
    sk_key = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456"
    assert "api03" not in redact_text(f"Key: {sk_key}")
    assert "[API_KEY_REDACTED]" in redact_text(f"Key: {sk_key}")

    # JWT
    jwt_token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    assert "eyJhbGci" not in redact_text(f"Auth: {jwt_token}")
    assert "[JWT_REDACTED]" in redact_text(f"Auth: {jwt_token}")

    # PEM Private Key
    pem_key = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA04sVf5...\n"
        "-----END RSA PRIVATE KEY-----"
    )
    assert "MIIEow" not in redact_text(pem_key)
    assert "[PRIVATE_KEY_REDACTED]" in redact_text(pem_key)


def test_negative_prose_not_redacted():
    # Conversational text / prose should not trigger false positive redaction
    prose1 = "secret: the plan is to deploy tomorrow"
    assert redact_text(prose1) == prose1

    prose2 = "the user password was reset yesterday by admin"
    assert redact_text(prose2) == prose2

    prose3 = "the authorization was granted to team members"
    assert redact_text(prose3) == prose3


def test_sensitive_markers():
    text = 'api_key = "secret-123"\npassword: "hunter2"\nghp_123456789012345678901234567890123456'
    markers = sensitive_markers(text)
    assert "api_key" in markers
    assert "password" in markers
    assert "github_token" in markers

    # Negative test for prose markers
    clean_text = "secret: the plan is ready. All features complete."
    assert sensitive_markers(clean_text) == []


def test_redact_payload_recursive():
    payload = {
        "headers": {"authorization": "Bearer secret-token"},
        "config": ["plain text", 'password: "top secret space"'],
        "int_val": 42,
    }
    redacted = redact_payload(payload)
    assert "secret-token" not in redacted["headers"]["authorization"]
    assert "top secret space" not in redacted["config"][1]
    assert redacted["int_val"] == 42
