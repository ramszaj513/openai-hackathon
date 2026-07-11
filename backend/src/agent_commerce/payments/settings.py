"""Validated environment settings for selecting a payment rail."""

from enum import StrEnum

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PaymentProvider(StrEnum):
    SIMULATOR = "simulator"
    STRIPE = "stripe"


class PaymentSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    payment_provider: PaymentProvider = PaymentProvider.SIMULATOR
    stripe_secret_key: SecretStr | None = None
    stripe_publishable_key: str | None = None
    stripe_payment_method: str = "pm_card_visa"
    stripe_decline_payment_method: str = "pm_card_visa_chargeDeclined"
    stripe_api_base: str = "https://api.stripe.com/v1"
    stripe_timeout_seconds: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def validate_stripe_configuration(self) -> "PaymentSettings":
        if self.payment_provider is not PaymentProvider.STRIPE:
            return self
        if self.stripe_secret_key is None:
            raise ValueError("STRIPE_SECRET_KEY is required when PAYMENT_PROVIDER=stripe")
        if not self.stripe_secret_key.get_secret_value().startswith("sk_test_"):
            raise ValueError("Only a Stripe test-mode secret key is accepted")
        if self.stripe_publishable_key is not None and not self.stripe_publishable_key.startswith(
            "pk_test_"
        ):
            raise ValueError("Only a Stripe test-mode publishable key is accepted")
        return self
