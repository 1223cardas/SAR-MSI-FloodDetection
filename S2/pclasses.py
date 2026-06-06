from dataclasses import dataclass
from pathlib import Path

@dataclass
class Product:
    name: str
    path: Path = Path()


@dataclass
class Bands:
    product: Product
    granule: str
    b3: str
    b8: str
    scl: str
