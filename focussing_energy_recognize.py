import cv2
import numpy as np
import logging
import os
import sys

# Setup logging
logger = logging.getLogger(__name__)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# The pattern image to be recognized
PATTERN_PATH = resource_path('assets/patterns/focusing_energy.png')

# Load pattern in grayscale
PATTERN_GRAY = cv2.imread(PATTERN_PATH, 0)
if PATTERN_GRAY is None:
    logger.warning(f"Could not load pattern image from {PATTERN_PATH}")

def find_pattern(frame, threshold=0.7, scales=np.linspace(0.4, 2.0, 30)[::-1]):
    """
    Finds the focusing_energy.png pattern in the given frame using grayscale multiscale matching.

    :param frame: The frame (image) to search in.
    :param threshold: The confidence threshold for a match. 
    :param scales: A range of scales to test. 30 steps between 0.4x and 2.0x.
    :return: A tuple (left, top, right, bottom) of the bounding box of the pattern if found, otherwise None.
    """
    if PATTERN_GRAY is None:
        logger.error(f"Pattern image not found at {PATTERN_PATH}")
        return None

    # Convert frame to grayscale
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    pattern_h, pattern_w = PATTERN_GRAY.shape[:2]
    
    best_match = None
    best_val = -1
    best_loc = None
    best_scale = 1.0

    # Multiscale template matching loop
    # Resize the pattern instead of the frame to keep coordinates relative to the original frame
    for scale in scales:
        width = int(pattern_w * scale)
        height = int(pattern_h * scale)
        
        # If the resized pattern is larger than the frame, we can't match it
        if width > frame_gray.shape[1] or height > frame_gray.shape[0] or width < 10 or height < 10:
            continue

        resized_pattern = cv2.resize(PATTERN_GRAY, (width, height))

        # Perform template matching using TM_CCOEFF_NORMED on pure grayscale
        # TM_CCOEFF_NORMED is highly robust to lighting changes as long as the texture matches
        res = cv2.matchTemplate(frame_gray, resized_pattern, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_scale = scale

    if best_val >= threshold and best_loc is not None:
        # The bounding box size is the size of the resized pattern that matched best
        orig_w = int(pattern_w * best_scale)
        orig_h = int(pattern_h * best_scale)

        left = best_loc[0]
        top = best_loc[1]
        right = left + orig_w
        bottom = top + orig_h
        
        logger.info(f"Pattern found with confidence {best_val:.2f} at scale {best_scale:.2f}")
        return left, top, right, bottom

    return None