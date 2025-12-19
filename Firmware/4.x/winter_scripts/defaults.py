"""Repository-wide defaults for `winter_scripts` extensions.

These values reflect the constraints you asked to enforce for all newly
generated code: always Pi 5, Arducam 64MP module, and lights disabled.
"""

PI_MODEL = 5
CAMERA_MODULE = "Arducam 64MP OwlSight OV64A40"
CAMERA_DOC_URL = "https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/64MP-OV64A40/"

# Do not actuate these relays from new scripts — lights/flash are disabled.
USE_LIGHTS = False
DISABLED_RELAYS = ["Relay_Ch2", "Relay_Ch3"]

# Default output directory for example scripts
DEFAULT_OUTPUT_DIR = "/tmp/mothbox_ext"
