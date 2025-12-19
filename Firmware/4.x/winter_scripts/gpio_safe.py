"""GPIO safety helpers used by `winter_scripts`.

This module centralizes the OFF/DEBUG pin logic used across the repo.
Do not change default pin numbers here without confirming with the owner.
"""
try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None

OFF_PIN = 16
DEBUG_PIN = 12


def ensure_gpio():
    if GPIO is None:
        raise RuntimeError("RPi.GPIO not available on this platform")


def setup(pins=(OFF_PIN, DEBUG_PIN)):
    ensure_gpio()
    GPIO.setmode(GPIO.BCM)
    for p in pins:
        GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def is_off():
    """Returns True if the OFF pin is tied to ground (device should not operate)."""
    if GPIO is None:
        return False
    GPIO.setup(OFF_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    return GPIO.input(OFF_PIN) == 0


def is_debug():
    """Returns True if the DEBUG pin is tied to ground."""
    if GPIO is None:
        return False
    GPIO.setup(DEBUG_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    return GPIO.input(DEBUG_PIN) == 0


def require_armed(func):
    """Decorator that raises RuntimeError when OFF pin is active.

    Use in new scripts to avoid running hardware when mothbox is turned OFF.
    """

    def wrapper(*args, **kwargs):
        if is_off():
            raise RuntimeError("Mothbox OFF pin active — aborting operation")
        return func(*args, **kwargs)

    return wrapper


if __name__ == "__main__":
    # quick smoke test that won't throw on non-RPi platforms
    try:
        setup()
        print("is_off() =>", is_off())
        print("is_debug() =>", is_debug())
    except RuntimeError as e:
        print(e)
