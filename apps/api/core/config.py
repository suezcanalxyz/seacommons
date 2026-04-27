# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings


class SuezCanalConfig(BaseSettings):
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
            return [x.strip() for x in v.split(",") if x.strip()]
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
