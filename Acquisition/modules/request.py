from requests_oauthlib import OAuth2Session
from shapely.geometry import shape, box
from datetime import datetime, timedelta

from .regiontimestamp import getTimeFrame
from .authsession import initSHSession
from .aclasses import SlugProduct, LogEntry
from .acquisition_config import *


def _printOrbitInfo(product: SlugProduct, productType: str) -> str:
	return f"(orbit {product.relative_orbit}/{product.orbit_state})" if productType == S1_COLLECTION else ""


def requestProducts(entry: LogEntry, productType: str) -> list[SlugProduct]:
	session = initSHSession()
	crisis_date_dt = datetime.strptime(entry.crisis_date, "%Y-%m-%dT%H:%M:%SZ")

	# --- Step 1: find the "after" product (closest acquisition following the crisis date) ---
	after = _find_after_product(entry, productType, crisis_date_dt, session)
	if after is None:
		print(
			f"Failed to find an 'after' product for crisis date {entry.crisis_date} "
			f"after expanding search to +/- 20 days."
		)
		return []

	if productType == S1_COLLECTION and after.relative_orbit is not None:
		before = _find_before_product_matching_orbit(
			entry, productType, crisis_date_dt, after, session
		)
	else:
		before = _find_before_product_any_orbit(entry, productType, crisis_date_dt, session)

	if before is None:
		print(
			f"Failed to find a suitable 'before' product for crisis date {entry.crisis_date}. "
			f"Searched up to {MAX_BEFORE_REPEAT_CYCLES} repeat cycles back."
		)
		return []

	print(
		f"Found products:\n"
		f"  Before: {before.id} {_printOrbitInfo(before, productType)}\n"
		f"  After:  {after.id} {_printOrbitInfo(after, productType)}"
	)

	entry.beforeId = before.id
	entry.afterId = after.id
	return [before, after]


# ---------------------------------------------------------------------------
# "After" product: simplest case — soonest acquisition after the crisis date,
# expanding the search window if nothing is found nearby.
# ---------------------------------------------------------------------------

def _find_after_product(
		entry: LogEntry, 
		productType: str, 
		crisis_date_dt: datetime, 
		session: OAuth2Session
	) -> SlugProduct | None:
	for delta in SEARCH_DELTAS:
		time_frame = getTimeFrame(crisis_date_dt, delta)
		if time_frame is None:
			continue

		current_date_range = time_frame.toString()
		print(f"Searching for 'after' product in range: {current_date_range}...")

		features = _searchFeatures(entry.bbox, current_date_range, productType, session)
		candidates = _toProducts(_filterByBbox(features, entry.bbox))

		after_candidates = [p for p in candidates if p.datetime > entry.crisis_date]
		if after_candidates:
			after = min(after_candidates, key=lambda p: p.datetime)
			entry.date_range = current_date_range
			print(f" |	Found 'after' product: {after.id} {_printOrbitInfo(after, productType)}")
			return after

		print(f"No 'after' product found within {delta} days. Expanding search window...")

	return None


# ---------------------------------------------------------------------------
# "Before" product, orbit-agnostic (used for Sentinel-2, or as last resort).
# ---------------------------------------------------------------------------

def _find_before_product_any_orbit(
	entry: LogEntry, productType: str, crisis_date_dt: datetime, session: OAuth2Session
) -> SlugProduct | None:
	for delta in SEARCH_DELTAS:
		time_frame = getTimeFrame(crisis_date_dt, delta)
		if time_frame is None:
			continue

		current_date_range = time_frame.toString()
		print(f"Searching for 'before' product in range: {current_date_range}...")
		features = _searchFeatures(entry.bbox, current_date_range, productType, session)
		candidates = _toProducts(_filterByBbox(features, entry.bbox))

		before_candidates = _filter_before_candidates(candidates, crisis_date_dt)
		if before_candidates:
			before = max(before_candidates, key=lambda p: p.datetime)
			print(f" |\tFound 'before' product: {before.id} {_printOrbitInfo(before, productType)}")
			return before

		print(f"No 'before' product found within {delta} days. Expanding search window...")

	return None


def _filter_before_candidates(candidates: list[SlugProduct], crisis_date_dt: datetime) -> list[SlugProduct]:
	cutoff_str = crisis_date_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
	return [p for p in candidates if p.datetime < cutoff_str]


# ---------------------------------------------------------------------------
# "Before" product, orbit-aware (Sentinel-1 only).
#
# Rationale: SAR backscatter depends on look geometry (incidence angle,
# layover/shadow/foreshortening), which only repeats when two acquisitions
# share the same relative orbit + orbit state (ascending/descending). On flat
# terrain a mismatched pair is usually fine; on hilly/mountainous terrain it
# introduces strong false change signal that has nothing to do with flooding.
#
# We search progressively further back in whole repeat-cycle increments
# (~12 days for Sentinel-1A/B) until we find a product on the same orbit as
# the "after" image, respecting a minimum buffer before the crisis date so we
# don't accidentally grab an image that's already showing early flood onset.
# ---------------------------------------------------------------------------

def _find_before_product_matching_orbit(
	entry: LogEntry, productType: str, crisis_date_dt: datetime,
	after: SlugProduct, session: OAuth2Session,
) -> SlugProduct | None:
	cycle = timedelta(days=S1_REPEAT_CYCLE_DAYS)

	print(f"Searching for 'before' product matching orbit {after.relative_orbit}/{after.orbit_state}...")

	earliest_dt = crisis_date_dt - (cycle * (MAX_BEFORE_REPEAT_CYCLES + 2))

	full_interval_str = f"{earliest_dt.isoformat()}Z/{crisis_date_dt.isoformat()}Z"

	features = _searchFeatures(entry.bbox, full_interval_str, productType, session)
	all_candidates = _toProducts(_filterByBbox(features, entry.bbox))

	valid_orbit_matches = [
		p for p in _filter_before_candidates(all_candidates, crisis_date_dt)
		if p.relative_orbit == after.relative_orbit
		and p.orbit_state == after.orbit_state
	]

	def get_prod_dt(p: SlugProduct):
		clean_ts = p.datetime.replace("Z", "+00:00")
		try:
			return datetime.fromisoformat(clean_ts)
		except ValueError:
			# Fallback for older python standard variations if milliseconds are messy
			return datetime.strptime(clean_ts.split(".")[0], "%Y-%m-%dT%H:%M:%S")

	# 3. Step through immediate pre-crisis window deltas (Local evaluation)
	for delta in SEARCH_DELTAS:
		time_frame = getTimeFrame(crisis_date_dt, delta)
		if time_frame is None:
			continue
			
		start_dt = datetime.fromisoformat(time_frame.start.replace("Z", "+00:00"))
		end_dt = datetime.fromisoformat(time_frame.end.replace("Z", "+00:00"))

		matched_in_delta = [p for p in valid_orbit_matches if start_dt <= get_prod_dt(p) <= end_dt]
		if matched_in_delta:
			before = max(matched_in_delta, key=get_prod_dt)
			print(f" |\tFound 'before' product: {before.id} {_printOrbitInfo(before, productType)}")
			return before

		print(f"No 'before' product found within {delta} days. Expanding search window...")

	# 4. Step through older repeat-cycle windows (Local evaluation)
	for n in range(1, MAX_BEFORE_REPEAT_CYCLES + 1):
		window_center = crisis_date_dt - (cycle * n)
		
		for delta in SEARCH_DELTAS:
			time_frame = getTimeFrame(window_center, delta)
			if time_frame is None:
				continue
				
			start_dt = datetime.fromisoformat(time_frame.start.replace("Z", "+00:00"))
			end_dt = datetime.fromisoformat(time_frame.end.replace("Z", "+00:00"))

			matched_in_cycle = [p for p in valid_orbit_matches if start_dt <= get_prod_dt(p) <= end_dt]
			if matched_in_cycle:
				before = max(matched_in_cycle, key=get_prod_dt)
				print(f" |\tFound 'before' product: {before.id} {_printOrbitInfo(before, productType)}")
				return before

			print(f"No 'before' product found within {delta} days. Expanding search window...")

	# 5. Fallback route if orbit geometry properties didn't intersect
	print(
		"No orbit-matched 'before' product found within "
		f"{MAX_BEFORE_REPEAT_CYCLES} repeat cycles. "
		"Falling back to closest available product regardless of orbit."
	)
	return _find_before_product_any_orbit(entry, productType, crisis_date_dt, session)


def _searchFeatures(bbox: list, date_range: str, productType: str, session: OAuth2Session) -> list:
	query = {
		"bbox": bbox,
		"datetime": date_range,
		"collections": [productType],
		"limit": DEFAULT_SEARCH_LIMIT,
	}
	# Cloud cover filtering for Sentinel-2
	if productType == S2_COLLECTION and DEFAULT_S2_CLOUD_COVER is not None:
		query["filter"] = f"eo:cloud_cover <= {DEFAULT_S2_CLOUD_COVER}"

	return fetchProducts(query, session)


def _toProducts(features: list) -> list[SlugProduct]:
	products = []
	for feature in features:
		props = feature.get("properties", {})
		dt_str = props.get("datetime")
		if not dt_str:
			continue

		relative_orbit = props.get("sat:relative_orbit")
		orbit_state = props.get("sat:orbit_state", "")

		products.append(
			SlugProduct(
				id=feature.get("id"),
				datetime=dt_str,
				relative_orbit=relative_orbit,
				orbit_state=orbit_state,
			)
		)
	return products


def _filterByBbox(features: list, bbox: list) -> list:
	return filter_features_fully_containing_bbox(features, bbox)


def fetchProducts(query, session: OAuth2Session) -> list:
	if not all(k in query for k in ("bbox", "datetime", "collections", "limit")):
		raise ValueError("Query must contain 'bbox', 'datetime', 'collections', and 'limit' keys.")

	try:
		response = session.post(CATALOG_URL, json=query)
		response.raise_for_status()
		results = response.json()

		features = results.get("features", [])
		# print("Search successful. Number of results:", len(features))
		return features
	except Exception as e:
		print("Error fetching products:", str(e))

	return []


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

		if covers or pct >= 90.0:
			remainder.append(feature)

	return remainder