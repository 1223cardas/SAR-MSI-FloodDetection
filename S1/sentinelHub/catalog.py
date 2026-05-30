from requests_oauthlib import OAuth2Session
from datetime import datetime, timedelta
from shapely.geometry import shape, box
from S1.sentinelHub.config import CATALOG_URL
from S1.sentinelHub.classes import Product


def getTimeFrame(crisisDate: str, daysMargin=5) -> str:
	crisisDate_dt = datetime.strptime(crisisDate, "%Y-%m-%dT%H:%M:%SZ")

	start_date = (crisisDate_dt - timedelta(days=daysMargin)).strftime("%Y-%m-%dT%H:%M:%SZ")
	end_date = (crisisDate_dt + timedelta(days=daysMargin)).strftime("%Y-%m-%dT%H:%M:%SZ")

	return f"{start_date}/{end_date}"


def getProducts(query, session: OAuth2Session) -> list:
	if not all(k in query for k in ("bbox", "datetime", "collections", "limit")):
		raise ValueError("Query must contain 'bbox', 'datetime', 'collections', and 'limit' keys.")

	try:
		response = session.post(CATALOG_URL, json=query)
		response.raise_for_status()
		results = response.json()

		features = results.get("features", [])
		print("Search successful. Number of results:", len(features))
		return features
	except Exception as e:
		print("Error fetching products:", str(e))

	return []


def select_products_around_date(features: list, crisis_date: str) -> tuple[Product, Product]:
	before: list[Product] = []
	after: list[Product] = []

	before_item = after_item = Product()

	for feature in features:
		props = feature.get("properties", {})

		dt_str = props.get("datetime")
		if not dt_str:
			continue

		item = Product(feature.get("id"), dt_str)
		after.append(item) if dt_str > crisis_date else before.append(item)

	try:
		before_item = max(before, key=lambda x: x.datetime)
		after_item = min(after, key=lambda x: x.datetime)
	except ValueError:
		print("No suitable products found around the crisis date.")

	return before_item, after_item


def filter_features_fully_containing_bbox(features: list, bbox: list) -> list:
	if not bbox or len(bbox) != 4:
		raise ValueError("bbox must be a list of four floats: [minx, miny, maxx, maxy]")

	bbox_geom = box(bbox[0], bbox[1], bbox[2], bbox[3])
	remainder = []

	for feature in features:
		feat_id = feature.get("id")
		geom = feature.get("geometry")

		if not geom:
			print(f"Feature {feat_id} has no geometry. Skipping.")
			continue

		try:
			feat_geom = shape(geom)
		except Exception as e:
			print(f"Error creating geometry for feature {feat_id}: {e}. Skipping.")
			continue

		inter = feat_geom.intersection(bbox_geom)
		pct = 100.0 * (inter.area / bbox_geom.area) if bbox_geom.area > 0 else 0.0

		covers = feat_geom.covers(bbox_geom)

		print(f"Feature {feat_id} covers {pct:.2f}% of the bbox.")
		if covers or pct >= 90.0:
			remainder.append(feature)

	return remainder
