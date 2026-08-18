"""
Unit tests for the spatialmedia CLI tool and PyQt6 helper wrappers using pathlib.

"""
# run with:
# python -m unittest discover -s tests

import sys
import unittest
from pathlib import Path

# Get the directory of this file, then get its parent (the project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Add the project root to the Python path if it isn't already there
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatialmedia import metadata_utils
from spatialmedia.__main__ import main

# Setup pathing constants relative to the tests directory structure
TESTS_DIR = PROJECT_ROOT / "tests"
DATA_DIR = TESTS_DIR / "data"
OUTPUT_DIR = TESTS_DIR / "test_output"


class TestAdd(unittest.TestCase):
    def inject_metadata(self, input_filename, output_filename, extra_cli_flags):
        # Create the test output directory if it doesn't exist yet
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        input_path = DATA_DIR / input_filename
        output_path = OUTPUT_DIR / output_filename

        # Verify the source mock file exists before passing to the CLI
        if not input_path.exists():
            raise FileNotFoundError(
                f"Missing required test asset in tests/data: {input_path}"
            )

        # Construct absolute string arguments for the legacy engine main function
        cli_args = ["-i"] + extra_cli_flags + [str(input_path), str(output_path)]

        self.assertIsNone(main(cli_args))

        if not output_path.exists():
            raise FileNotFoundError(
                f"Test execution failed to output target file at: {output_path}"
            )

        contents = []
        metadata_utils.parse_metadata(str(output_path), lambda x: contents.append(x))

        # Clean up output artifacts immediately
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            return ""

        return "\n".join(contents[2:])

    def test_inject_v1_equirect_mono(self):
        contents = self.inject_metadata(
            input_filename="testsrc_320x240_h264.mp4",
            output_filename="equirect_mono_v1.mp4",
            extra_cli_flags=["--projection", "equirectangular"],
        )

        self.assertFalse(contents.find("SV3D") >= 0)
        self.assertFalse(contents.find("PRHD") >= 0)
        self.assertFalse(contents.find("EQUI") >= 0)
        self.assertFalse(contents.find("ST3D") >= 0)
        self.assertTrue(contents.find("ProjectionType = equirectangular") > 0)

    def test_inject_v1_rectangular_left_right(self):
        contents = self.inject_metadata(
            input_filename="testsrc_320x240_h264.mp4",
            output_filename="rectangular_left_right_v1.mp4",
            extra_cli_flags=["--stereo", "left-right", "--projection", "none"],
        )

        self.assertFalse(contents.find("SV3D") >= 0)
        self.assertFalse(contents.find("PRHD") >= 0)
        self.assertFalse(contents.find("EQUI") >= 0)
        self.assertFalse(contents.find("ST3D") >= 0)
        self.assertFalse(contents.find("ProjectionType = equirectangular") > 0)
        self.assertTrue(contents.find("ProjectionType = rectangular") > 0)
        self.assertTrue(contents.find("Spherical = false") > 0)

    def test_inject_v2_equirect_mono(self):
        contents = self.inject_metadata(
            input_filename="testsrc_320x240_h264.mp4",
            output_filename="equirect_mono.mp4",
            extra_cli_flags=["--v2", "--projection", "equirectangular"],
        )
        self.assertTrue(contents.find("SV3D") >= 0)
        self.assertTrue(contents.find("SVHD") >= 0)
        self.assertTrue(contents.find("Spherical Metadata Tool") >= 0)
        self.assertTrue(contents.find("PRHD") >= 0)
        self.assertTrue(contents.find("EQUI") >= 0)
        self.assertFalse(contents.find("ST3D") >= 0)
        self.assertTrue(contents.find("Bounds Top: 0") >= 0)
        self.assertTrue(contents.find("Bounds Bottom: 0") >= 0)
        self.assertTrue(contents.find("Bounds Left: 0") >= 0)
        self.assertTrue(contents.find("Bounds Right: 0") >= 0)

    def test_inject_v2_equirect_mono_with_bounds(self):
        contents = self.inject_metadata(
            input_filename="testsrc_320x240_h264.mp4",
            output_filename="equirect_mono.mp4",
            extra_cli_flags=[
                "--v2",
                "--bounds",
                "0x1:-2:0x7FFFFFFF:32",
                "--projection",
                "equirectangular",
            ],
        )
        self.assertTrue(contents.find("SV3D") >= 0)
        self.assertTrue(contents.find("SVHD") >= 0)
        self.assertTrue(contents.find("Spherical Metadata Tool") >= 0)
        self.assertTrue(contents.find("PRHD") >= 0)
        self.assertTrue(contents.find("EQUI") >= 0)
        self.assertFalse(contents.find("ST3D") >= 0)
        self.assertTrue(contents.find("Bounds Top: 1") >= 0)
        self.assertTrue(contents.find("Bounds Bottom: 0") >= 0)
        self.assertTrue(contents.find("Bounds Left: 2147483647") >= 0)
        self.assertTrue(contents.find("Bounds Right: 32") >= 0)

    def test_inject_v2_rectangular_left_right(self):
        contents = self.inject_metadata(
            input_filename="testsrc_320x240_h264.mp4",
            output_filename="rectangular_left_right.mp4",
            extra_cli_flags=["--v2", "--stereo", "left-right", "--projection", "none"],
        )
        self.assertFalse(contents.find("SV3D") >= 0)
        self.assertFalse(contents.find("PRHD") >= 0)
        self.assertFalse(contents.find("EQUI") >= 0)
        self.assertTrue(contents.find("ST3D") >= 0)
        self.assertTrue(contents.find("Stereo Mode: 2") >= 0)


class TestGenerateSphericalXml(unittest.TestCase):
    def test_default_projection_is_equirectangular(self):
        xml = metadata_utils.generate_spherical_xml("equirectangular", None)
        if isinstance(xml, bytes):
            xml = xml.decode("utf-8")
        self.assertIn("equirectangular", xml)
        self.assertIn("<GSpherical:Spherical>true</GSpherical:Spherical>", xml)

    def test_none_projection_is_not_spherical(self):
        xml = metadata_utils.generate_spherical_xml("none", None)
        if isinstance(xml, bytes):
            xml = xml.decode("utf-8")
        self.assertNotIn("equirectangular", xml)
        self.assertIn("<GSpherical:Spherical>false</GSpherical:Spherical>", xml)


if __name__ == "__main__":
    unittest.main()
