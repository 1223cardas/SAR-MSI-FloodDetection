from pathlib import Path
from types import SimpleNamespace
from requests_oauthlib import OAuth2Session
from S1.sentinelHub.config import ZIPPER_ODATA, FILTER_LIST_URL, OUTPUT_DIR
from tqdm import tqdm


def resolve_products_uuids(product_names: list[str], session: OAuth2Session) -> tuple[dict[str, str], list[str]]:
	if not product_names:
		return {}, []

	payload = {"FilterProducts": [{"Name": name} for name in product_names]}
	resp = session.post(FILTER_LIST_URL, json=payload)
	resp.raise_for_status()

	items = resp.json().get("value", [])
	found = {
		item["Name"]: item["Id"] 
		for item in items 
		if "Name" in item and "Id" in item
	}
	missing = [name for name in product_names if name not in found]

	return found, missing


def _build_download_url(product_id: str) -> str:
	return f"{ZIPPER_ODATA}/Products({product_id})/$value"


def _auth_headers(session: OAuth2Session) -> dict[str, str]:
	headers = dict(session.headers)
	access_token = (session.token or {}).get("access_token")
	if access_token:
		headers["Authorization"] = f"Bearer {access_token}"
	return headers


MB = 1024 * 1024

def download_product(product_id: str, out_path: Path, session: OAuth2Session) -> Path:
	url = _build_download_url(product_id)
	headers = _auth_headers(session)
	resp = session.get(url, headers=headers, stream=True)
	resp.raise_for_status()

	out_path.parent.mkdir(parents=True, exist_ok=True)

	total = int(resp.headers.get("Content-Length", 0))
	with open(out_path, "wb") as f:
		with tqdm(total=total, unit="B", unit_scale=True, desc=f"Downloading {product_id}...") as pbar:
			for chunk in resp.iter_content(chunk_size=16 * MB):
				if chunk:
					f.write(chunk)
					pbar.update(len(chunk))
	return out_path


def download_products(products: list[SimpleNamespace], session: OAuth2Session) -> list[Path]:
	paths = []
	for prod in products:
		try:
			output = OUTPUT_DIR / f"{prod.id}.zip"

			path = download_product(prod.uuid, output, session)
			print(f"Downloaded {prod.id} to {path}")

			paths.append(path)
		except Exception as e:
			print(f"Failed to download {prod.id}: {e}")
	exit()
	return paths
