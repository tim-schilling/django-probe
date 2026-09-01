from __future__ import annotations

import math
import os

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured
from sentry_sdk.integrations.django import DjangoIntegration

DEFAULT_TRACES_SAMPLE_RATE = 0.1


def _traces_sample_rate() -> float:
    raw_value = os.environ.get(
        "SENTRY_TRACES_SAMPLE_RATE", str(DEFAULT_TRACES_SAMPLE_RATE)
    )
    try:
        sample_rate = float(raw_value)
    except ValueError as error:
        raise ImproperlyConfigured(
            "SENTRY_TRACES_SAMPLE_RATE must be a number between 0 and 1"
        ) from error

    if not math.isfinite(sample_rate) or not 0 <= sample_rate <= 1:
        raise ImproperlyConfigured(
            "SENTRY_TRACES_SAMPLE_RATE must be a number between 0 and 1"
        )
    return sample_rate


def initialize_sentry() -> bool:
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT") or None,
        integrations=[
            DjangoIntegration(
                transaction_style="url",
                middleware_spans=True,
                signals_spans=True,
                cache_spans=True,
            )
        ],
        max_request_body_size="never",
        release=os.environ.get("SENTRY_RELEASE") or None,
        send_default_pii=False,
        traces_sample_rate=_traces_sample_rate(),
    )
    return True
