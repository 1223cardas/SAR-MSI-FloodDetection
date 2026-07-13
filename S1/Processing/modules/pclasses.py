from dataclasses import dataclass
import numpy.ma as ma
import rasterio


@dataclass
class ProductData:
    band: ma.MaskedArray
    transform: rasterio.Affine
    crs: rasterio.CRS | None
    height: int
    width: int


@dataclass
class StackBands:
    vh_mst: str = ""
    vv_mst: str = ""
    vh_slv: str = ""
    vv_slv: str = ""
    elevation: str = ""
    land_cover: str = ""
