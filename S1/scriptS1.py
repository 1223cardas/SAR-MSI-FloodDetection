from .utilS1 import *
import numpy as np
import subprocess
import sys, math
import rasterio
from rasterio.enums import Resampling
from pathlib import Path
import os



def processProducts(gptExec, paths):
	singleProduct = getWorkflow("singleProductProcessing")
	stackProducts = getWorkflow("stackProducts")

	products = getProducts()
	roi = getShapeFile()

	print("Starting pre processing products...")
	for product in products:

		print(f"Processing product: {product.name}")
		product_file = getProductFile(product.path)

		output_file = build_file(paths["cache"], f"zone_{product.date.strftime('%Y%m%d')}_PROCESSING")
		
		# Check for cached product before processing
		cached_file = Path(str(output_file).replace("_PROCESSING", "")).with_suffix('.dim')
		if cached_file.exists():
			print(f"Cached product found for {product.name}, skipping processing.")
			continue

		cmd = gptExec.copy()
		cmd.extend([
			str(singleProduct),
			f"-Pproduct={str(product_file)}",
			f"-Poutput={str(output_file)}",
			f"-PvectorFile={str(roi)}",
		])

		execute_command(
			cmd,
			success_message=f"Successfully processed product {product.name}.\n" \
			f"Output saved to {output_file}",
			error_message=f"Error processing product {product.name}:"
		)

		refactor_snap_product(str(output_file))	


	cachedProducts = sorted(paths["cache"].glob("zone_*.dim"))
	print("Finished processing products.")
	print("Stacking products and creating flood mask...")

	# DEPOIS
	out = build_file(paths["out"], 'flood_zone')

	variables = computeWorkflowVariables(cachedProducts)

	cmd = gptExec.copy()
	cmd.extend([
		str(stackProducts),
		f"-Pproduct1={str(cachedProducts[0])}",
		f"-Pproduct2={str(cachedProducts[1])}",
		f"-Pvh_slv={variables['vh_slv']}",
		f"-Pvh_mst={variables['vh_mst']}",
		f"-Pvv_mst={variables['vv_mst']}",
		f"-Pvh_diff={variables['vh_diff']}",
		f"-Pvv_diff={variables['vv_diff']}",
		f"-Poutput={str(out)}"
	])

	try:
		subprocess.run(cmd, check=True)
		print(f"Flood mask created. Output saved to {out}")
	except subprocess.CalledProcessError as e:
		print(f"Error running stack workflow: \n{e.stderr}")

	return




def calculateAndDisplayResults(gptExec, paths) -> Path:
	visualize = paths["workflows"] / "calculateArea.xml"
	tifs = list(paths["out"].glob("floodImage*.tif"))

	if not tifs:
		floodZone = choose_from_list(
			list(paths["out"].glob("flood_zone*.dim")), select_count=1,
			prompt="No existing flood image found. Select a product to visualize:"
		)

		image = build_file(paths["out"], "floodImage")
		print(f"Generating flood image TIF, this may take a moment...")
		cmd = gptExec.copy()

		cmd.extend([
			str(visualize),
			f"-Pproduct={str(floodZone[0])}",
			f"-Poutput={str(image)}"
		])

		try:
			subprocess.run(cmd, check=True)
			tif_path = str(image) + ".tif"
		except subprocess.CalledProcessError as e:
			raise RuntimeError(f"Error running visualization workflow: \n{e.stderr}")
		
	elif len(tifs) > 1:
		tif_path = choose_from_list(
			tifs, select_count=1,
			prompt="Multiple flood images found. Please select one to view:"
		)[0]
	else:
		tif_path = tifs[0]

	data = rasterio.open(tif_path)

	# --- Calculate Flooded Area ---
	band = data.read(1, masked=True)

	# Count the pixels with a value of 1 (indicating flood)
	flood_count = int(np.count_nonzero(band == 1))
	EARTH_RADIUS_M = 6378137.0

	# Calculate Area in square meters (approximate for Geographic CRS, exact if Projected)
	if data.crs and data.crs.is_geographic:
		bounds = data.bounds
		center_lat = (bounds.top + bounds.bottom) / 2.0
		lat_rad = math.radians(center_lat)

		# Approx. Earth radius in meters
		meters_per_deg_lat = (math.pi / 180.0) * EARTH_RADIUS_M
		meters_per_deg_lon = (math.pi / 180.0) * EARTH_RADIUS_M * math.cos(lat_rad)

		px_area_m2 = abs((data.transform.a * meters_per_deg_lon) * (data.transform.e * meters_per_deg_lat))
	else:
		px_area_m2 = abs(data.transform.a * data.transform.e)
	total_area_m2 = flood_count * px_area_m2

	print("\n--- Flood Calculation Results ---")
	print(f"Number of Flooded Pixels: {flood_count:,}")
	print(f"Estimated Pixel Size: ~{px_area_m2:,.2f} m²")
	print(f"Total Flooded Area: {total_area_m2:,.2f} m² ({total_area_m2 / 1000000.0:,.3f} km²)\n")

	# Save a downsampled PNG for faster viewing instead of plotting the full TIFF
	preview_path = Path(paths["out"]) / f"{Path(tif_path).stem}_preview.png"
	max_dim = 8192
	try:
		with rasterio.open(tif_path) as src:
			height = src.height
			width = src.width
			scale = min(1.0, max_dim / max(height, width))
			out_h = max(1, int(height * scale))
			out_w = max(1, int(width * scale))
			arr = src.read(1, out_shape=(out_h, out_w), resampling=Resampling.bilinear)
			mn = np.nanmin(arr)
			mx = np.nanmax(arr)
			if mx <= mn:
				arr8 = np.zeros_like(arr, dtype='uint8')
			else:
				arr8 = ((arr - mn) / (mx - mn) * 255.0).astype('uint8')

			profile = src.profile.copy()
			for key in ("blockxsize", "blockysize", "tiled", "interleave"):
				profile.pop(key, None)
			profile.update(driver='PNG', dtype=rasterio.uint8, count=1, height=out_h, width=out_w)
			preview_path.parent.mkdir(parents=True, exist_ok=True)
			with rasterio.open(preview_path, 'w', **profile) as dst:
				dst.write(arr8[np.newaxis, :, :])

		print(f"Preview image saved to {preview_path}")
		try:
			os.startfile(str(preview_path))
		except Exception:
			pass
	except Exception as e:
		print(f"Failed to create preview image: {e}")

	return tif_path



def main():
	# Suppress stack traces for cleaner error messages
	sys.tracebacklimit = 0