from enum import Enum

MODE_CONFIG = {
    "all": {
        "title": "Pipeline Completo",
        "fields": [
            ("Pasta Sentinel-2", "s2_dir"),
            ("Output S2",        "s2_out"),
            ("Threshold",        "threshold"),
            ("S1 TIF",           "s1_tif"),
            ("S2 TIF",           "s2_tif"),
            ("Output final",     "out_tif"),
        ],
    },
    "auto": {
        "title": "Pipeline automático",
        "fields": [],
    },
    "s1": {
        "title": "Pipeline Sentinel-1",
        "fields": [],
    },
    "s2": {
        "title": "Pipeline Sentinel-2",
        "fields": [
            ("Pasta Sentinel-2", "s2_dir"),
            ("Output S2",        "s2_out"),
            ("Threshold",        "threshold"),
        ],
    },
    "fusion": {
        "title": "Fusão",
        "fields": [
            ("S1 TIF",       "s1_tif"),
            ("S2 TIF",       "s2_tif"),
            ("Output final", "out_tif"),
        ],
    },
}

FIELD_DEFAULTS = {
    "s2_dir":    "Imagens",
    "s2_out":    "ndwi_work",
    "threshold": "",
    "s1_tif":    "S1/output/kherson_flood.tif",
    "s2_tif":    "ndwi_work/flood.tif",
    "out_tif":   "flood_fused_continuous.tif",
}

class RunState(Enum):
    IDLE           = "IDLE"
    RUNNING        = "RUNNING"
    PAUSED         = "PAUSED"
    AWAITING_INPUT = "AWAITING_INPUT"
    COMPLETED      = "COMPLETED"
    FAILED         = "FAILED"
    CANCELED       = "CANCELED"

class PromptCancelledError(RuntimeError):
    pass