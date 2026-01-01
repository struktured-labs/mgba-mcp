"""Test the MGBAEmulator wrapper."""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mgba_mcp.emulator import MGBAEmulator, validate_png


def test_validate_png():
    """Test PNG validation to prevent corrupted images from crashing Claude API."""
    print("Testing PNG validation...")

    # Valid minimal PNG (1x1 black pixel)
    # PNG signature + IHDR + IDAT + IEND
    valid_png_1x1 = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk length + type
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 dimensions
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # bit depth, color type, etc + CRC
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0x00, 0x00, 0x00,
        0x01, 0x00, 0x01, 0x00, 0x05, 0xFE, 0xF4, 0xDC,
        0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,  # IEND chunk
        0xAE, 0x42, 0x60, 0x82,
    ])

    # Test cases
    test_cases = [
        (b"", False, "empty data"),
        (b"not a png", False, "random bytes"),
        (b"\x89PNG\r\n\x1a\n", False, "just signature, no chunks"),
        (valid_png_1x1[:-4], False, "truncated PNG (missing IEND CRC)"),
        (valid_png_1x1[:-12], False, "truncated PNG (missing IEND)"),
        (b"GIF89a" + b"\x00" * 100, False, "GIF file"),
    ]

    # Try to load a real PNG from the tmp directory for more realistic testing
    test_png_path = Path(__file__).parent.parent.parent / "tmp/test_screenshot.png"
    if test_png_path.exists():
        real_png = test_png_path.read_bytes()
        test_cases.append((real_png, True, "real screenshot from test"))
        # Also test truncated version
        test_cases.append((real_png[:len(real_png)//2], False, "truncated real screenshot"))

    all_passed = True
    for data, expected, description in test_cases:
        result = validate_png(data)
        passed = result == expected
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {description} -> {result} (expected {expected})")
        if not passed:
            all_passed = False

    return all_passed


def test_corrupted_screenshot_handling():
    """Test that corrupted screenshots don't get returned."""
    print("Testing corrupted screenshot handling...")

    rom_path = Path(__file__).parent.parent.parent / "rom/working/penta_dragon_dx_FIXED.gb"
    if not rom_path.exists():
        print(f"  ROM not found: {rom_path}")
        return True  # Skip test if ROM not available

    emu = MGBAEmulator()
    try:
        # Run a normal test - should get a valid screenshot
        result = emu.run_frames(str(rom_path), frames=30, screenshot=True)

        if result.success and result.screenshot:
            # Verify the screenshot is valid PNG
            is_valid = validate_png(result.screenshot)
            print(f"  Screenshot returned is valid PNG: {is_valid}")
            if not is_valid:
                print(f"  ERROR: Emulator returned invalid PNG!")
                return False
            return True
        else:
            print(f"  No screenshot returned (error: {result.error})")
            return False
    finally:
        emu.cleanup()


def test_run_frames():
    """Test running for a fixed number of frames."""
    rom_path = Path(__file__).parent.parent.parent / "rom/working/penta_dragon_dx_FIXED.gb"
    if not rom_path.exists():
        print(f"ROM not found: {rom_path}")
        return False

    emu = MGBAEmulator()
    try:
        print(f"Testing run_frames with {rom_path}...")
        result = emu.run_frames(str(rom_path), frames=30, screenshot=True)

        print(f"  Success: {result.success}")
        print(f"  Screenshot: {len(result.screenshot) if result.screenshot else 0} bytes")
        print(f"  Error: {result.error}")

        if result.screenshot:
            # Save for inspection
            out_path = Path(__file__).parent.parent.parent / "tmp/test_screenshot.png"
            out_path.write_bytes(result.screenshot)
            print(f"  Saved screenshot to {out_path}")

        return result.success and result.screenshot is not None
    finally:
        emu.cleanup()


def test_dump_oam():
    """Test OAM dump with savestate."""
    rom_path = Path(__file__).parent.parent.parent / "rom/working/penta_dragon_dx_FIXED.gb"
    ss_path = Path(__file__).parent.parent.parent / "rom/working/penta_dragon_dx_FIXED.ss1"

    if not rom_path.exists():
        print(f"ROM not found: {rom_path}")
        return False
    if not ss_path.exists():
        print(f"Savestate not found (optional): {ss_path}")
        ss_path = None
    else:
        ss_path = str(ss_path)

    emu = MGBAEmulator()
    try:
        print(f"Testing dump_oam...")
        result = emu.dump_oam(str(rom_path), savestate_path=ss_path, frames_before_dump=30)

        print(f"  Success: {result.success}")
        print(f"  Data: {result.data is not None}")
        print(f"  Error: {result.error}")

        if result.data and "oam" in result.data:
            visible_sprites = [s for s in result.data["oam"] if s["visible"]]
            print(f"  Visible sprites: {len(visible_sprites)}")

        return result.success
    finally:
        emu.cleanup()


def test_read_memory():
    """Test memory reading."""
    rom_path = Path(__file__).parent.parent.parent / "rom/working/penta_dragon_dx_FIXED.gb"

    if not rom_path.exists():
        print(f"ROM not found: {rom_path}")
        return False

    emu = MGBAEmulator()
    try:
        print(f"Testing read_memory...")
        # Read boss flag and some OAM
        result = emu.read_memory(str(rom_path), addresses=[0xFFBF, 0xFE00, 0xFE01], frames_before_read=30)

        print(f"  Success: {result.success}")
        print(f"  Data: {result.data}")
        print(f"  Error: {result.error}")

        return result.success and result.data is not None
    finally:
        emu.cleanup()


if __name__ == "__main__":
    print("=" * 50)
    print("mGBA Emulator Wrapper Tests")
    print("=" * 50)

    tests = [
        ("validate_png", test_validate_png),
        ("corrupted_screenshot_handling", test_corrupted_screenshot_handling),
        ("run_frames", test_run_frames),
        ("dump_oam", test_dump_oam),
        ("read_memory", test_read_memory),
    ]

    results = []
    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            results.append((name, False))

    print("\n" + "=" * 50)
    print("Results:")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(p for _, p in results)
    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    sys.exit(0 if all_passed else 1)
