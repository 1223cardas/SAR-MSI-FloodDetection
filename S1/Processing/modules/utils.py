import re
from datetime import datetime
from S1.Processing.modules.pclasses import Product

def extractDateFromProduct(product: Product) -> datetime:
	# Assuming the product name format is something like "S1A_IW_GRDH_1SDV_20210101T123456_20210101T123456_012345_67890_ABCDE.SAFE"
	# The date is usually in the format YYYYMMDDTHHMMSS
	match = re.search(r"_(\d{8}T\d{6})_", product.name)
	if not match:
		raise ValueError(f"Could not parse acquisition time from: {product.name}")

	result = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
	# print(f"|\tExtracted acquisition time: {result} from {product.name}")
	return result