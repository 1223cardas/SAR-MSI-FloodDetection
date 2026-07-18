from dataclasses import dataclass

from common.shared_models import Product


@dataclass
class Bands:
	product: Product
	granule: str
	b3: str
	b8: str
	scl: str
