import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from finbrief_analyzer.collect.models import CollectError
from finbrief_analyzer.collect.ports import RateProvider
from finbrief_analyzer.collect.rates import DEFAULT_SERIES, EcosRateProvider, EcosSeries

TODAY = date(2026, 10, 7)
KEY = "SECRETKEY0123456789A"
KTB3Y = EcosSeries(symbol="KR3YT", stat_code="817Y002", item_code="010200000")
# Any: JSON documents.
SAMPLE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "ecos_rate.json").read_text(encoding="utf-8")
)
NO_DATA = {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}
BAD_KEY = {"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키가 유효하지 않습니다."}}


def _provider(
    handler: Callable[[httpx.Request], httpx.Response],
    series: tuple[EcosSeries, ...] = (KTB3Y,),
) -> EcosRateProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return EcosRateProvider(client, SecretStr(KEY), today=lambda: TODAY, series=series)


def test_latest_and_previous_values_become_a_quote() -> None:
    # given
    provider = _provider(lambda request: httpx.Response(200, json=SAMPLE))

    # when
    (quote,) = provider.get_rates()

    # then
    assert quote.symbol == "KR3YT"
    assert quote.close == pytest.approx(3.961)
    assert quote.prev_close == pytest.approx(3.933)
    assert quote.as_of == date(2026, 10, 7)


def test_request_path_carries_series_codes_and_the_lookback_window() -> None:
    # given
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=SAMPLE)

    # when
    _provider(handler).get_rates()

    # then
    assert paths == [
        f"/api/StatisticSearch/{KEY}/json/kr/1/100/817Y002/D/20260927/20261007/010200000"
    ]


def test_invalid_key_response_raises_collect_error() -> None:
    # given: ECOS reports errors with HTTP 200
    provider = _provider(lambda request: httpx.Response(200, json=BAD_KEY))

    # when / then
    with pytest.raises(CollectError, match="INFO-100"):
        provider.get_rates()


def test_no_data_response_raises_collect_error() -> None:
    # given
    provider = _provider(lambda request: httpx.Response(200, json=NO_DATA))

    # when / then
    with pytest.raises(CollectError, match="no data"):
        provider.get_rates()


def test_empty_row_list_raises_collect_error() -> None:
    # given
    body = {"StatisticSearch": {"list_total_count": 0, "row": []}}
    provider = _provider(lambda request: httpx.Response(200, json=body))

    # when / then
    with pytest.raises(CollectError, match="no data"):
        provider.get_rates()


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(lambda request: httpx.Response(500), id="http-500"),
        pytest.param(lambda request: httpx.Response(200, text="<html>"), id="not-json"),
        pytest.param(lambda request: httpx.Response(200, json=BAD_KEY), id="bad-key"),
        pytest.param(lambda request: httpx.Response(200, json=[1, 2]), id="wrong-shape"),
        pytest.param(
            lambda request: httpx.Response(200, json={"StatisticSearch": {}}), id="no-rows-key"
        ),
    ],
)
def test_api_key_in_the_url_never_reaches_the_error(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    # given: the key is part of the URL path, and httpx errors quote the URL
    provider = _provider(handler)

    # when
    with pytest.raises(CollectError) as caught:
        provider.get_rates()

    # then: neither the message nor a chained exception carries it
    assert KEY not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_timeout_is_translated_to_collect_error_without_the_url() -> None:
    # given
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"timed out: {request.url}")

    # when
    with pytest.raises(CollectError) as caught:
        _provider(handler).get_rates()

    # then
    assert "ReadTimeout" in str(caught.value)
    assert KEY not in str(caught.value)
    assert caught.value.__context__ is None


def test_failed_series_is_left_out_while_the_others_are_returned() -> None:
    # given
    fx = EcosSeries(symbol="USD/KRW", stat_code="731Y001", item_code="0000001")

    def handler(request: httpx.Request) -> httpx.Response:
        if "731Y001" in request.url.path:
            return httpx.Response(200, json=NO_DATA)
        return httpx.Response(200, json=SAMPLE)

    # when
    quotes = _provider(handler, series=(fx, KTB3Y)).get_rates()

    # then
    assert [q.symbol for q in quotes] == ["KR3YT"]


def test_rows_with_unreadable_values_are_skipped() -> None:
    # given
    rows = [
        {"TIME": "20261006", "DATA_VALUE": "3.933"},
        {"TIME": "20261007", "DATA_VALUE": ""},
        {"TIME": "bad", "DATA_VALUE": "1"},
        {"DATA_VALUE": "1"},
    ]
    body = {"StatisticSearch": {"row": rows}}
    provider = _provider(lambda request: httpx.Response(200, json=body))

    # when
    (quote,) = provider.get_rates()

    # then
    assert quote.as_of == date(2026, 10, 6)
    assert quote.prev_close is None


def test_default_series_cover_kr_rates_and_the_usd_krw_base_rate() -> None:
    # given / when
    symbols = [s.symbol for s in DEFAULT_SERIES]

    # then: FX comes from ECOS, not from the quote adapters (PoC decision)
    assert symbols == ["KR_BASE_RATE", "KR3YT", "KR10YT", "USD/KRW"]


def test_provider_satisfies_the_rate_port() -> None:
    # given / when
    provider: RateProvider = _provider(lambda request: httpx.Response(200, json=SAMPLE))

    # then
    assert provider.name == "ecos"
