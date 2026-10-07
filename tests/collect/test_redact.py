import logging

import pytest
from pydantic import SecretStr

from finbrief_analyzer.collect.redact import hide_from_http_log


def test_registered_secret_is_masked_in_http_client_log_records(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # given
    hide_from_http_log(SecretStr("s3cr3t-value"))

    # when
    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx").info("HTTP Request: GET %s", "https://x/?api_token=s3cr3t-value")

    # then
    assert "s3cr3t-value" not in caplog.text
    assert "api_token=***" in caplog.text


def test_percent_encoded_form_of_the_secret_is_masked_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # given: a secret with characters a URL has to escape
    hide_from_http_log(SecretStr("a/b+c="))

    # when
    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx").info("GET https://x/?key=a%2Fb%2Bc%3D and path /a/b+c=/json")

    # then
    assert "a%2Fb%2Bc%3D" not in caplog.text
    assert "a/b+c=" not in caplog.text


def test_records_without_a_secret_are_left_untouched(caplog: pytest.LogCaptureFixture) -> None:
    # given
    hide_from_http_log(SecretStr("another-secret"))

    # when
    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx").info("HTTP Request: GET %s %d", "https://x/feed", 200)

    # then
    assert caplog.records[-1].getMessage() == "HTTP Request: GET https://x/feed 200"
    assert caplog.records[-1].args == ("https://x/feed", 200)


def test_empty_secret_does_not_mask_everything(caplog: pytest.LogCaptureFixture) -> None:
    # given
    hide_from_http_log(SecretStr(""))

    # when
    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx").info("plain message")

    # then
    assert caplog.records[-1].getMessage() == "plain message"


def test_registering_twice_installs_one_filter() -> None:
    # given / when
    hide_from_http_log(SecretStr("one"))
    hide_from_http_log(SecretStr("two"))

    # then
    names = [type(f).__name__ for f in logging.getLogger("httpx").filters]
    assert names.count("_SecretFilter") == 1
