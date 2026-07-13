from enum import Enum

MODE_CONFIG = {
    "auto": {
        "title": "Automatic pipeline",
        "fields": [],
    },
    "s1": {
        "title": "Sentinel-1 pipeline",
        "fields": [],
    },
    "s2": {
        "title": "Sentinel-2 pipeline",
        "fields": [
            ("S2 output file", "s2_out"),
            ("Threshold", "threshold"),
        ],
    },
    "fusion": {
        "title": "S1 and S2 Fusion",
        "fields": [
            ("S1 TIF",       "s1_tif"),
            ("S2 TIF",       "s2_tif"),
            ("Final output", "out_tif"),
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
