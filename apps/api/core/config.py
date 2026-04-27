# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
import json
from typing import Any, Tuple, Type
from pydantic import field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
from pydantic_settings.sources import EnvSettingsSource


class _SafeEnvSource(EnvSettingsSource):
    """Treats empty strings as absent for complex (list/dict) fields.

    pydantic-settings v2 calls json.loads on every non-None value for
    complex-typed fields, so passing WITNESS_ENDPOINTS="" from Docker
    raises a SettingsError before our field_validators ever run.
    """

    def prepare_field_value(
        self, field_name: str, field: FieldInfo, value: Any, value_is_complex: bool
    ) -> Any:
        # _field_is_complex is the authoritative check; value_is_complex arg may be False
        # even for list[str] fields, so we must use _field_is_complex here.
        is_complex, _ = self._field_is_complex(field)
        if (is_complex or value_is_complex) and isinstance(value, str) and not value.strip():
            return None
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class SuezCanalConfig(BaseSettings):

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _SafeEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )
    REDIS_URL: str = "redis://localhost:6379/0"
    DATABASE_URL: str = "postgresql://suez:canal@localhost:5432/suezcanal"
    WITNESS_ENDPOINTS: list[str] = []
    INFRASOUND_ENABLED: bool = False
    INFRASOUND_DEVICE: str = "rboom"
    INFRASOUND_STA_WINDOW: float = 1.0
    INFRASOUND_LTA_WINDOW: float = 30.0
    INFRASOUND_TRIGGER_RATIO: float = 3.5
    SEISMIC_ENABLED: bool = False
    SEISMIC_DEVICE: str = "adxl355"
    HYDRO_ENABLED: bool = False
    SDR_ENABLED: bool = False
    SDR_THRESHOLD_DB: float = 10.0
    ADSB_ENABLED: bool = False
    ADSB_DEVICE: str = "rtlsdr"
    TID_ENABLED: bool = False
    TID_REGION_LAT: float = 35.5
    TID_REGION_LON: float = 18.0
    TID_REGION_RADIUS_KM: int = 2000
    TID_POLL_INTERVAL_S: int = 60
    TID_MIN_STATIONS: int = 3
    TID_IGS_MIRROR: str = "https://cddis.nasa.gov/archive/gnss/data/hourly"
    TID_CORS_REGIONS: list[str] = ["EUREF", "MED"]
    GNSS_ENABLED: bool = True
    CORRELATION_CONFIDENCE_ALERT: float = 0.55
    CORRELATION_CONFIDENCE_URGENT: float = 0.80
    CMEMS_USERNAME: str = ""
    CMEMS_PASSWORD: str = ""
    CMEMS_CURRENT_DATASET: str = "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"
    CMEMS_TEMPERATURE_DATASET: str = "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m"
    CMEMS_WAVE_DATASET: str = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
    OPEN_METEO_BASE: str = "https://api.open-meteo.com/v1"
    AISSTREAM_KEY: str = ""
    ADSB_EXCHANGE_KEY: str = ""
    GPSJAM_URL: str = "https://gpsjam.org/geo.json"
    ACLED_KEY: str = ""
    MADRIGAL_URL: str = "https://madrigal.haystack.mit.edu"
    EMSC_WS: str = "wss://www.seismicportal.eu/standing_order/websocket"
    MOCK: bool = False
    DEMO_PUBLIC_MODE: bool = False

    # TimeZero Professional bridge
    TIMEZERO_ENABLED: bool = False
    TIMEZERO_HOST: str = "localhost"
    TIMEZERO_PORT: int = 4371
    TIMEZERO_AUTO_PUSH: bool = True
    TIMEZERO_EXPORT_DIR: str | None = None
    TIMEZERO_API_KEY: str | None = None

    @field_validator("WITNESS_ENDPOINTS", "TID_CORS_REGIONS", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                import json
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed if str(x).strip()]
                except json.JSONDecodeError:
                    pass
            return [x.strip() for x in stripped.split(",") if x.strip()]
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


config = SuezCanalConfig()

if __name__ == "__main__":
    print("SuezCanalConfig loaded OK")
    print(f"  MOCK={config.MOCK}")
    print(f"  AISSTREAM_KEY={'SET' if config.AISSTREAM_KEY else 'NOT SET (mock fallback)'}")
    print(f"  TID_ENABLED={config.TID_ENABLED}")
