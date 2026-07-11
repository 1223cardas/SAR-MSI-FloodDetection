from requests_oauthlib import OAuth2Session
from requests import Response
from pathlib import Path
from tqdm import tqdm
import zipfile


from mainconfig import OUTPUT_DIR
from .authsession import initCDSESession
from .aclasses import Product
from .acquisition_config import *


def _createDownloadURL(uuid: str) -> str:
	return f"{ODATA_ZIPPER_URL}/Products({uuid})/$value"


def _downloadFile(resp: Response, location: Path):
	total = int(resp.headers.get("Content-Length", 0))
	with location.open("wb") as f:
		with tqdm(total=total, unit="B", unit_scale=True, desc=f"Downloading...") as pbar:
			for chunk in resp.iter_content(chunk_size=8 * MB):
				if chunk:
					f.write(chunk)
					pbar.update(len(chunk))


def _checkIfDownloaded(products: list[Product]) -> list[Product]:
	""" Checks the products list and returns a list of products that arent yet downloaded. """
	productsToDownload: list[Product] = []

	for prod in products:
		product_folder = OUTPUT_DIR / f"{prod.id}"

		# If the folder does not exist, queue for download.
		if not product_folder.exists():
			print(f"Product {prod.id} not found at {product_folder}. Will be queued for download.")
			productsToDownload.append(prod)
			continue

	return productsToDownload


def _extract_zip(zip_path: Path, downloadedProducts: list):
	try:
		print("Extracting zip", zip_path)
		with zipfile.ZipFile(zip_path, 'r') as z:
			z.extractall(OUTPUT_DIR)
		try:
			zip_path.unlink()
		except Exception:
			pass
		extracted_path = OUTPUT_DIR / f"{zip_path.stem}.SAFE"
		downloadedProducts.append(extracted_path)

	except zipfile.BadZipFile:
		print(f"Downloaded file for {zip_path.stem} is not a valid zip archive; keeping {zip_path} for manual inspection.")
		downloadedProducts.append(zip_path)


def _resolveUUIDs(products: list[Product], session: OAuth2Session):
	""" Adds uuid values to every product in the products list """
	for prod in products:
		if not prod.id:
			print(f"Product {prod} is missing an ID. Skipping UUID resolution.")
			continue

		try:
			payload = {"FilterProducts": [{"Name": prod.id}]}
			resp = session.post(FILTER_LIST_URL, json=payload)
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



MB = 1024 * 1024
def _downloadProducts(products: list[Product], session: OAuth2Session) -> list[Path]:
	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	
	downloaded_productPaths = []
	for prod in products:
		if not prod.uuid:
			print(f"Product {prod.id} is missing a UUID. Skipping download.")
			continue
		
		zip_path = OUTPUT_DIR / f"{prod.id.removesuffix('.SAFE')}.zip"
		if zip_path.exists():
			print(f"Product {prod.id} already exists at {zip_path}. Skipping download.")
			downloaded_productPaths.append(zip_path)
			continue

		try:
			download_url = _createDownloadURL(prod.uuid)

			resp = session.get(download_url, headers=session.headers, stream=True)
			resp.raise_for_status()

			print(f"Starting download of product {prod.id} to {zip_path}...")
			_downloadFile(resp, zip_path)
			print(f"Downloaded {prod.id} to {zip_path}")

			_extract_zip(zip_path, downloaded_productPaths)

		except Exception as e:
			print(f"Error downloading product {prod.id}: {e}")
			continue
	
	return downloaded_productPaths



def queueProductsForDownload(products: list[Product]):
	productsToDownload = _checkIfDownloaded(products)

	if not productsToDownload: 
		print("All products already downloaded. No downloads queued.")
		return

	opt = input("Queue products for download? [y/n]")
	if opt not in ("y", "yes"):
		print("Download skipped")
		return

	session = initCDSESession()

	_resolveUUIDs(productsToDownload, session)
	_downloadProducts(productsToDownload, session)
