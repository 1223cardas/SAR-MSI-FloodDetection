import os
import subprocess
from unittest.mock import patch, MagicMock
import numpy as np
import pytest
import rasterio
from rasterio import transform

# --- MOCK FUNCTIONS TO SIMULATE YOUR PIPELINE UTILITIES ---
# (If importing directly from your src, replace these with: from your_module import ...)
def compute_tile_otsu(array: np.ndarray) -> float:
    """Simulates Otsu thresholding calculation on an array, ignoring NaNs."""
    clean_array = array[~np.isnan(array)]
    if clean_array.size == 0:
        return -3.0
    # Simple mock threshold split for testing
    return float(np.mean(clean_array))

def run_snap_graph(xml_path: str, params: dict) -> bool:
    """Simulates invoking the SNAP GPT command line tool."""
    cmd = ["gpt", xml_path]
    for key, val in params.items():
        cmd.append(f"-P{key}={val}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.returncode == 0


# --- PYTEST FIXTURES ---

@pytest.fixture
def dummy_raster_data():
    """Generates a clean synthetic 10x10 radar backscatter difference matrix."""
    # Simulating a background close to 0 dB (no change) and an inundated patch (-5 dB)
    data = np.zeros((10, 10), dtype=np.float32)
    data[3:7, 3:7] = -5.0  # Inundated zone
    data[0, 0] = np.nan    # Include a NaN value to test resilience
    return data

@pytest.fixture
def temp_geotiff(tmp_path, dummy_raster_data):
    """Creates a physical temporary GeoTIFF file to test rasterio interactions."""
    file_path = tmp_path / "dummy_input.tif"
    
    meta = {
        "driver": "GTiff",
        "dtype": "float32",
        "nodata": np.nan,
        "width": 10,
        "height": 10,
        "count": 1,
        "crs": "EPSG:4326",
        "transform": transform.from_origin(0, 10, 1, 1)
    }
    
    with rasterio.open(file_path, "w", **meta) as dst:
        dst.write(dummy_raster_data, 1)
        
    return file_path


# --- TEST CASES ---

class TestRasterProcessing:

    def test_compute_tile_otsu_valid_data(self, dummy_raster_data):
        """Validates that the threshold logic correctly processes numeric arrays and handles NaNs."""
        threshold = compute_tile_otsu(dummy_raster_data)
        
        # The mean of our dummy array should be negative due to the mock flood patch
        assert isinstance(threshold, float)
        assert threshold < 0.0

    def test_compute_tile_otsu_all_nan(self):
        """Ensures the algorithm fallback works when a tile contains only NaN/NoData values."""
        nan_array = np.full((5, 5), np.nan, dtype=np.float32)
        threshold = compute_tile_otsu(nan_array)
        
        # Should return the safe default threshold fallback
        assert threshold == -3.0


class TestPipelineOrchestration:

    @patch("subprocess.run")
    def test_run_snap_graph_success(self, mock_sub_run):
        """Verifies that the GPT executor constructs and passes the correct XML parameters."""
        # Mocking successful subprocess execution
        mock_sub_run.return_value = MagicMock(returncode=0, stdout="Execution finished successfully")
        
        xml_file = "createMask.xml"
        parameters = {
            "product": "stack.dim",
            "vh_threshold_tif": "vh_otsu.tif",
            "output": "output_flood.dim"
        }
        
        success = run_snap_graph(xml_file, parameters)
        
        assert success is True
        # Verify subprocess was called with the correct structure
        called_args = mock_sub_run.call_args[0][0]
        assert "gpt" in called_args
        assert "createMask.xml" in called_args
        assert "-Pproduct=stack.dim" in called_args
        assert "-Pvh_threshold_tif=vh_otsu.tif" in called_args

    @patch("subprocess.run")
    def test_run_snap_graph_failure(self, mock_sub_run):
        """Ensures that CI catches runtime execution failures from the SNAP GPT executable."""
        # Configure mock to raise a CalledProcessError (simulating a SNAP crash)
        mock_sub_run.side_effect = subprocess.CalledProcessError(
            returncode=1, 
            cmd="gpt", 
            stderr="Error: NullPointerException in BandMaths operator"
        )
        
        with pytest.raises(subprocess.CalledProcessError):
            run_snap_graph("createMask.xml", {"product": "corrupted.dim"})


class TestRasterIOIntegrity:

    def test_geotiff_metadata_matching(self, temp_geotiff):
        """Verifies raster metadata profile reading, protecting against shifting coordinates or datatypes."""
        assert os.path.exists(temp_geotiff)
        
        with rasterio.open(temp_geotiff) as src:
            assert src.count == 1
            assert src.dtypes[0] == "float32"
            assert np.isnan(src.nodata)
            
            # Read profile back as matrix
            matrix = src.read(1)
            assert matrix.shape == (10, 10)
            assert matrix[5, 5] == -5.0  # Verify target pixel value integrity



