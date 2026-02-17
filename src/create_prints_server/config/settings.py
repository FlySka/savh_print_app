from dataclasses import dataclass


@dataclass(frozen=True)
class FilterConfig:
    use_config_date: bool
    config_date: str | None
    timezone: str


@dataclass(frozen=True)
class OutputConfig:
    pdf_orders_path: str
    pdf_guides_path: str
    title: str
    subtitle: str
    max_items: int
    contact: str
    logo_path: str | None = None


def parse_filter_config(cfg: dict) -> FilterConfig:
    return FilterConfig(
        use_config_date=bool(cfg.get("USE_CONFIG_DATE", False)),
        config_date=cfg.get("CONFIG_DATE"),
        timezone=cfg.get("TIMEZONE", "America/Santiago"),
    )
