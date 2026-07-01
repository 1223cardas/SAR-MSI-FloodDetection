from requests_oauthlib import OAuth2Session
from shapely.geometry import shape, box
from datetime import datetime, timedelta

from .regiontimestamp import getTimeFrame
from .authsession import initSHSession
from .aclasses import Product, LogEntry
from . import aquisition_config


def requestProducts(entry: LogEntry, productType: str) -> list[Product]:
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

	# Sentinel-2 has no fixed relative-orbit revisit constraint comparable to S1's
	# 12-day repeat cycle in the same way SAR look-geometry does — orbit matching
	# only matters for SAR backscatter comparability, so only enforce it for S1.
	if productType == aquisition_config.S1_COLLECTION and after.relative_orbit is not None:
		before = _find_before_product_matching_orbit(
			entry, productType, crisis_date_dt, after, session
		)
	else:
		before = _find_before_product_any_orbit(entry, productType, crisis_date_dt, session)

	if before is None:
		print(
			f"Failed to find a suitable 'before' product for crisis date {entry.crisis_date}. "
			f"Searched up to {aquisition_config.MAX_BEFORE_REPEAT_CYCLES} repeat cycles back."
		)
		return []

	print(
		f"Success: before={before.id} (orbit {before.relative_orbit}/{before.orbit_state}), "
		f"after={after.id} (orbit {after.relative_orbit}/{after.orbit_state})"
	)

	entry.beforeId = before.id
	entry.afterId = after.id
	return [before, after]


# ---------------------------------------------------------------------------
# "After" product: simplest case — soonest acquisition after the crisis date,
# expanding the search window if nothing is found nearby.
# ---------------------------------------------------------------------------

def _find_after_product(
	entry: LogEntry, productType: str, crisis_date_dt: datetime, session: OAuth2Session
) -> Product | None:
	search_deltas = [5, 10, 20]

	for delta in search_deltas:
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
			return after

		print(f"No 'after' product found within {delta} days. Expanding search window...")

	return None


# ---------------------------------------------------------------------------
# "Before" product, orbit-agnostic (used for Sentinel-2, or as last resort).
# ---------------------------------------------------------------------------

def _find_before_product_any_orbit(
	entry: LogEntry, productType: str, crisis_date_dt: datetime, session: OAuth2Session
) -> Product | None:
	search_deltas = [5, 10, 20]

	for delta in search_deltas:
		time_frame = getTimeFrame(crisis_date_dt, delta)
		if time_frame is None:
			continue

		current_date_range = time_frame.toString()
		features = _searchFeatures(entry.bbox, current_date_range, productType, session)
		candidates = _toProducts(_filterByBbox(features, entry.bbox))

		before_candidates = _applyMinBuffer(candidates, entry.crisis_date)
		if before_candidates:
			return max(before_candidates, key=lambda p: p.datetime)

	return None


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
	after: Product, session: OAuth2Session,
) -> Product | None:
	cycle = timedelta(days=aquisition_config.S1_REPEAT_CYCLE_DAYS)
	buffer = timedelta(days=aquisition_config.MIN_BEFORE_BUFFER_DAYS)
	latest_allowed = crisis_date_dt - buffer

	for n in range(1, aquisition_config.MAX_BEFORE_REPEAT_CYCLES + 1):
		# Search a window centered on (crisis_date - n*cycle), wide enough to
		# tolerate the satellite's actual revisit jitter (+/- a couple days).
		window_center = crisis_date_dt - (cycle * n)
		time_frame = getTimeFrame(window_center, daysMargin=3)
		if time_frame is None:
			continue

		current_date_range = time_frame.toString()
		# print(
		# 	f"Searching for orbit-matched 'before' product "
		# 	f"(~{aquisition_config.S1_REPEAT_CYCLE_DAYS * n} days back): {current_date_range}..."
		# )

		features = _searchFeatures(entry.bbox, current_date_range, productType, session)
		candidates = _toProducts(_filterByBbox(features, entry.bbox))

		matched = [
			p for p in candidates
			if p.relative_orbit == after.relative_orbit
			and p.orbit_state == after.orbit_state
			and p.datetime <= latest_allowed.strftime("%Y-%m-%dT%H:%M:%SZ")
		]

		if matched:
			# Closest-in-time match on the correct orbit, within the buffer.
			return max(matched, key=lambda p: p.datetime)

	print(
		f"No orbit-matched 'before' product found within "
		f"{aquisition_config.MAX_BEFORE_REPEAT_CYCLES} repeat cycles. "
		"Falling back to closest available product regardless of orbit."
	)
	return _find_before_product_any_orbit(entry, productType, crisis_date_dt, session)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _applyMinBuffer(candidates: list[Product], crisis_date: str) -> list[Product]:
	"""Keep only candidates dated before crisis_date minus the minimum buffer."""
	crisis_dt = datetime.strptime(crisis_date, "%Y-%m-%dT%H:%M:%SZ")
	cutoff = crisis_dt - timedelta(days=aquisition_config.MIN_BEFORE_BUFFER_DAYS)
	cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
	return [p for p in candidates if p.datetime <= cutoff_str]


def _searchFeatures(bbox: list, date_range: str, productType: str, session: OAuth2Session) -> list:
	query = {
		"bbox": bbox,
		"datetime": date_range,
		"collections": [productType],
		"limit": aquisition_config.DEFAULT_SEARCH_LIMIT,
	}
	return fetchProducts(query, session)


def _toProducts(features: list) -> list[Product]:
	products = []
	for feature in features:
		props = feature.get("properties", {})
		dt_str = props.get("datetime")
		if not dt_str:
			continue

		relative_orbit = props.get("sat:relative_orbit")
		orbit_state = props.get("sat:orbit_state", "")

		products.append(Product(
			id=feature.get("id"),
			datetime=dt_str,
			relative_orbit=relative_orbit,
			orbit_state=orbit_state,
		))
	return products


def _filterByBbox(features: list, bbox: list) -> list:
	return filter_features_fully_containing_bbox(features, bbox)


def fetchProducts(query, session: OAuth2Session) -> list:
	if not all(k in query for k in ("bbox", "datetime", "collections", "limit")):
		raise ValueError("Query must contain 'bbox', 'datetime', 'collections', and 'limit' keys.")

	try:
		response = session.post(aquisition_config.CATALOG_URL, json=query)
		response.raise_for_status()
		results = response.json()

		features = results.get("features", [])
		print("Search successful. Number of results:", len(features))
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