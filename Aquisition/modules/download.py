from requests_oauthlib import OAuth2Session
from pathlib import Path
from tqdm import tqdm
from Aquisition.modules.classes import Product
from Aquisition.modules.authsession import initCDSESession
from Aquisition.modules import config
from mainconfig import input

def checkIfDownloaded(products: list[Product]) -> list[Path]:
	paths = []
	for prod in products:
		output = config.OUTPUT_DIR / f"{prod.id}.zip"
		if output.exists():
			print(f"Product {prod.id} already exists. Skipping download.")
			paths.append(output)
		else:
			print(f"Product {prod.id} not found at {output}. Will be queued for download.")
	
	return paths



def resolveUUIDs(products: list[Product], session: OAuth2Session) -> list[Product]:
	for prod in products:
		if not prod.id:
			print(f"Product {prod} is missing an ID. Skipping UUID resolution.")
			continue

		try:
			payload = {"FilterProducts": [{"Name": prod.id}]}
			resp = session.post(config.FILTER_LIST_URL, json=payload)
			resp.raise_for_status()

			items = resp.json().get("value", [])
			if items:
				prod.uuid = items[0].get("Id", "")
				if not prod.uuid:
					print(f"Product {prod.id} found but missing 'Id' in response.")

			else:
				print(f"Product {prod.id} not found in response.")

		except Exception as e:
			print(f"Error resolving UUID for product {prod.id}: {e}")
			continue

	return products



MB = 1024 * 1024
def downloadProducts(products: list[Product], session: OAuth2Session) -> list[Path]:
	output_dir = config.OUTPUT_DIR
	output_dir.mkdir(parents=True, exist_ok=True)
	
	paths = []
	for prod in products:
		if not prod.uuid:
			print(f"Product {prod.id} is missing a UUID. Skipping download.")
			continue
		
		output = output_dir / f"{prod.id}.zip"
		if output.exists():
			print(f"Product {prod.id} already exists at {output}. Skipping download.")
			paths.append(output)
			continue

		try:
			download_url = f"{config.ODATA_ZIPPER_URL}/Products({prod.uuid})/$value"

			resp = session.get(download_url, headers=session.headers, stream=True)
			resp.raise_for_status()

			output.parent.mkdir(parents=True, exist_ok=True)
			print(f"Starting download of product {prod.id}...")

			total = int(resp.headers.get("Content-Length", 0))
			with output.open("wb") as f:
				with tqdm(total=total, unit="B", unit_scale=True, desc=f"Downloading...") as pbar:
					for chunk in resp.iter_content(chunk_size=8 * MB):
						if chunk:
							f.write(chunk)
							pbar.update(len(chunk))

			print(f"Downloaded {prod.id} to {output}")
			paths.append(output)
		except Exception as e:
			print(f"Error downloading product {prod.id}: {e}")
			continue
	
	return paths

def queueProductsForDownload(products: list[Product]) -> list[Path]:
	checked_paths = checkIfDownloaded(products)
	if len(checked_paths) == len(products):
		print("All products already downloaded. No downloads queued.")
		return checked_paths
		
	opt = input("Queue products for download? [y/n]\n" + config.CLI_PROMPT).strip().lower()
	if opt not in ("y", "yes"):
		print("Download skipped")
		return []

	session = initCDSESession()

	resolveUUIDs(products, session)
	return downloadProducts(products, session)
