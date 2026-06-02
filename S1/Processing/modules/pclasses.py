from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import numpy.ma as ma
import rasterio


@dataclass
class Product:
    name: str
    path: Path = Path()
    date: datetime = datetime.min

    def parseDate(self) -> str:
        """Converts the product's acquisition datetime to the format used in SNAP band names: DDMmmYYYY (ex: 01Jan2020)."""
        return self.date.strftime("%d%b%Y")


@dataclass
class ProductData:
    band: ma.MaskedArray
    transform: rasterio.Affine
    crs: rasterio.CRS | None
    height: int
    width: int
