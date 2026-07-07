from enum import Enum

MODE_CONFIG = {
    "all": {
        "title": "Pipeline Completo",
        "fields": [
            ("output S2",        "s2_out"),
            ("Threshold",        "threshold"),
            ("S1 TIF",           "s1_tif"),
            ("S2 TIF",           "s2_tif"),
            ("output final",     "out_tif"),
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
            ("output S2",        "s2_out"),
            ("Threshold",        "threshold"),
        ],
    },
    "fusion": {
        "title": "Fusão",
        "fields": [
            ("S1 TIF",       "s1_tif"),
            ("S2 TIF",       "s2_tif"),
            ("output final", "out_tif"),
        ],
    },
}

FIELD_DEFAULTS = {
    "s2_out":    "S2/output",
    "threshold": "",
    "s1_tif":    "S1/output/kherson_flood.tif",
    "s2_tif":    "",
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