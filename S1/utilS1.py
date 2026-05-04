from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os, shutil
import glob
import re

# Define a simple data class to hold product information
@dataclass 
class Product:
	name: str
	path: Path
	date: datetime

def check_directories() -> dict[str, Path]:
	""" Check and create necessary directories, and return a dictionary of the paths """
	print("Checking directories...", end=" ")
	BASE_PATH = Path(__file__).parent.resolve()

	OUT_DIR = 		BASE_PATH / "out"
	DATA_DIR = 		BASE_PATH / "data"
	CACHE_DIR = 	BASE_PATH / "cache"
	PRODUCT_DIR = 	DATA_DIR / "products"
	ROI_DIR = 		DATA_DIR / "region_of_interest"
	WORKFLOW_DIR = 	BASE_PATH / "workflows"


	if CACHE_DIR.exists() and any(CACHE_DIR.iterdir()):
		print(f"|	Clearing cache to avoid conflicts...")
		shutil.rmtree(CACHE_DIR)

	paths = {
		"base": BASE_PATH,
		"out": OUT_DIR,
		"data": DATA_DIR,
		"cache": CACHE_DIR,
		"products": PRODUCT_DIR,
		"roi": ROI_DIR,
		"workflows": WORKFLOW_DIR
	}

	for d in paths.values():
		if not d.exists():
			print(f"|	{d} doesn't exist. Creating directory...")
			d.mkdir(parents=True, exist_ok=True)

	print("Done.")
	return paths



def choose_from_list(items: list[Path], select_count: int = 1, prompt: str | None = None) -> list[Path]:
	"""
		Prompt the user to select one or more items from a list of Path objects.\n
		Returns a list of the selected Path objects (length == select_count).
	"""
	if not items:
		raise ValueError("No items available to select from.")

	if prompt:
		print(prompt)


	for i, item in enumerate(items, start=1):
		print(f"\t[{i}] {item.name}")

	while True:
		inp = input(f"Enter {select_count} number{'s' if select_count != 1 else ''} separated by a comma (e.g. 1{',2' if select_count>1 else ''}): ").strip()
		parts = re.split(r"\s*,\s*", inp)

		if len(parts) != select_count:
			print(f"Please enter exactly {select_count} number{'s' if select_count != 1 else ''}.")
			continue

		try:
			idxs = [int(p) for p in parts]
		except ValueError:
			print("Invalid input. Use numbers like '1' or '1,2'.")
			continue

		if any(i not in range(1, len(items) + 1) for i in idxs):
			print("One or more numbers are out of range. Try again.")
			continue

		if len(set(idxs)) != len(idxs):
			print("Duplicate selection detected. Please choose distinct items.")
			continue

		return [items[i - 1] for i in idxs]



# Function to locate the SNAP GPT executable
def getExecutable() -> Path:
	print("Locating SNAP GPT executable...")
	snap_dir = os.getenv("SNAP_DIRECTORY")

	# If SNAP_DIRECTORY is set, check if gpt.exe exists there
	if snap_dir:
		candidate = Path(snap_dir)
		gpt_exec = candidate / "bin" / "gpt.exe"

		if gpt_exec.exists():
			print(f"|	Found gpt.exe at: {gpt_exec}")
			return gpt_exec
		
		raise FileNotFoundError(
			f"SNAP_DIRECTORY is set to '{snap_dir}', but gpt.exe was not found.\n"
			"Verify SNAP_DIRECTORY in your .env points to the SNAP installation root."
		)

	raise FileNotFoundError(
		"SNAP_DIRECTORY environment variable is not set.\n"
		"Please set SNAP_DIRECTORY in your .env to your SNAP installation directory,\n"
		"or install SNAP at the default location: C:\\Program Files\\snap."
	)



def getProducts(data: Path) -> list[Product]:
	print("Discovering products...")

	entries = list(data.iterdir())

	if not entries:
		raise FileNotFoundError(
			"No products found in data/.\n"
			"Please add at least two Sentinel-1 products (.SAFE or .zip) to the data/products/ directory."
		)

	valid_candidates: list[Path] = []

	for candidate in entries:
		is_safe = candidate.is_dir() and candidate.name.upper().endswith(".SAFE")
		is_zip = candidate.is_file() and candidate.suffix.lower() == ".zip"
		if is_safe or is_zip:
			valid_candidates.append(candidate)
		else:
			print(
				f"|	Invalid product found in data/: {candidate.name}.\n"
				"|	Only .SAFE directories or .zip files are accepted. This entry will be ignored." 
			)


	if len(valid_candidates) < 2:
		raise FileNotFoundError(
			"At least two Sentinel-1 products (.SAFE or .zip) " \
			"are required in data/products/ folder."
		)


	# If there are more than two valid products, ask the user to select two.
	selected_candidates: list[Path]
	if len(valid_candidates) > 2:
		selected_candidates = choose_from_list(
				valid_candidates, select_count=2,
				prompt="More than two valid products found. Please select two to use:"
			)
	else:
		selected_candidates = valid_candidates

	products: list[Product] = []
	for candidate in selected_candidates:
		acquisition_date = getDate(candidate)
		products.append(Product(name=candidate.name, path=candidate, date=acquisition_date))

	products.sort(key=lambda p: p.date)
	return products



def getDate(product: Path) -> datetime:
	match = re.search(r"_(\d{8}T\d{6})_", product.name)
	if not match:
		raise ValueError(f"Could not parse acquisition time from: {product.name}")
	
	result = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
	print(f"|	Extracted acquisition time: {result} from {product.name}")
	return result



def getProductFile(product: Path) -> Path:
	# If it's a .SAFE directory, return the manifest.safe file inside it
	if product.is_dir() and product.name.upper().endswith(".SAFE"):
		manifest = product / "manifest.safe"
		if not manifest.exists():
			raise FileNotFoundError(f"SAFE manifest not found: {manifest}")
		return manifest
	
	# If it's a .zip file, return it directly
	return product


def getShapeFile(data: Path) -> Path:
	# Look for .shp files in the specified directory
	shape_files = sorted(data.glob("*.shp"))

	if not shape_files:
		raise FileNotFoundError(
			"No .shp file found in data/region_of_interest/. " \
			"Please add a shapefile to this directory."
		)
	
	if len(shape_files) > 1:
		selected = choose_from_list(
				shape_files, select_count=1,
				prompt="Multiple .shp files found in data/region_of_interest. Please select one:"
			)
		return selected[0]

	return shape_files[0]


def build_file(dir: Path, base_name: str) -> Path:
	path = dir / base_name
	filesInDir = glob.glob(str(f"{path}*.*"))

	if not filesInDir:
		return path
	
	if "cache" in str(dir):
		print(f"creating cache file {path}...")

		# check if there are any files with the same base name and remove them
		if filesInDir:
			print(f"Warning: {path} already exists. Removing existing file to avoid conflicts.")
			(shutil.rmtree(Path(p)) if Path(p).is_dir() else Path(p).unlink() for p in filesInDir)

		return path

	pattern = re.compile(rf"^{re.escape(base_name)}_(\d{{1,3}})(?:\.[^.]+)?$")
	
	max_idx = 0
	matched_any = False
	existing_names = set(Path(f).stem for f in filesInDir)
	
	for name in existing_names:
		if name == base_name:
			matched_any = True
			continue
			
		match = pattern.search(name)
		if match:
			matched_any = True
			max_idx = max(max_idx, int(match.group(1)))
			
	if not matched_any:
		return path

	next_index = max_idx + 1
	
	new_path = dir / f"{base_name}_{next_index:03d}"
	print(f"Warning: files matching '{base_name}' already exist. Using index {next_index:03d} to avoid overwriting.")
	return new_path