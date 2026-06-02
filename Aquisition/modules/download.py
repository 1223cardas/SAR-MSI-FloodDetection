from requests_oauthlib import OAuth2Session
from pathlib import Path
from tqdm import tqdm

from Aquisition.modules.aclasses import Product
from Aquisition.modules.authsession import initCDSESession
from Aquisition.modules import aquisition_config
from mainconfig import input, OUTPUT_DIR
import zipfile

def checkIfDownloaded(products: list[Product]) -> list[Path]:
	product_paths = []
	for prod in products:
		product_folder = OUTPUT_DIR / f"{prod.id}"

		if product_folder.exists() and any(product_folder.iterdir()):
			product_paths.append(product_folder)
		else:
			print(f"Product {prod.id} not found at {product_folder}. Will be queued for download.")
	
	return product_paths



def resolveUUIDs(products: list[Product], session: OAuth2Session) -> list[Product]:
	for prod in products:
		if not prod.id:
			print(f"Product {prod} is missing an ID. Skipping UUID resolution.")
			continue

		try:
			payload = {"FilterProducts": [{"Name": prod.id}]}
			resp = session.post(aquisition_config.FILTER_LIST_URL, json=payload)
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
	output_dir = OUTPUT_DIR
	output_dir.mkdir(parents=True, exist_ok=True)
	
	downloaded_productPaths = []
	for prod in products:
		if not prod.uuid:
			print(f"Product {prod.id} is missing a UUID. Skipping download.")
			continue
		
		zip_path = output_dir / f"{prod.id.removesuffix(".SAFE")}.zip"
		if zip_path.exists():
			print(f"Product {prod.id} already exists at {zip_path}. Skipping download.")
			downloaded_productPaths.append(zip_path)
			continue

		try:
			download_url = f"{aquisition_config.ODATA_ZIPPER_URL}/Products({prod.uuid})/$value"

			resp = session.get(download_url, headers=session.headers, stream=True)
			resp.raise_for_status()

			print(f"Starting download of product {prod.id} to {zip_path}...")

			total = int(resp.headers.get("Content-Length", 0))
			with zip_path.open("wb") as f:
				with tqdm(total=total, unit="B", unit_scale=True, desc=f"Downloading...") as pbar:
					for chunk in resp.iter_content(chunk_size=8 * MB):
						if chunk:
							f.write(chunk)
							pbar.update(len(chunk))

			print(f"Downloaded {prod.id} to {zip_path}")

			# extract zip into product folder and remove zip
			product_folder = output_dir / f"{prod.id}"
			product_folder.mkdir(parents=True, exist_ok=True)

			try:
				with zipfile.ZipFile(zip_path, 'r') as z:
					z.extractall(product_folder)
				print(f"Extracted {prod.id} into {product_folder}")
				try:
					zip_path.unlink()
				except Exception:
					pass
				downloaded_productPaths.append(product_folder)

			except zipfile.BadZipFile:
				print(f"Downloaded file for {prod.id} is not a valid zip archive; keeping {zip_path} for manual inspection.")
				downloaded_productPaths.append(zip_path)
		except Exception as e:
			print(f"Error downloading product {prod.id}: {e}")
			continue
	
	return downloaded_productPaths



def queueProductsForDownload(products: list[Product]) -> list[Path]:
	checked_paths = checkIfDownloaded(products)
	if len(checked_paths) == len(products):
		print("All products already downloaded. No downloads queued.")
		return checked_paths
		
	opt = input("Queue products for download? [y/n]", expected_type=str)
	if opt not in ("y", "yes"):
		print("Download skipped")
		return []

	session = initCDSESession()

	resolveUUIDs(products, session)
	return downloadProducts(products, session)
