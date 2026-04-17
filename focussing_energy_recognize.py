import cv2

# The pattern image to be recognized
PATTERN_PATH = 'assets/patterns/focusing_energy.png'
PATTERN = cv2.imread(PATTERN_PATH, 0)
if PATTERN is not None:
    # Binarize the pattern image using Otsu's thresholding
    _, PATTERN_BIN = cv2.threshold(PATTERN, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    PATTERN_WIDTH, PATTERN_HEIGHT = PATTERN_BIN.shape[::-1]
else:
    # Handle case where image is not loaded, perhaps by raising an error or logging a warning
    print(f"Warning: Could not load pattern image from {PATTERN_PATH}")
    PATTERN_BIN = None
    PATTERN_WIDTH, PATTERN_HEIGHT = 0, 0


def find_pattern(frame, threshold=0.8):
    """
    Finds the focusing_energy.png pattern in the given frame using binarization.

    :param frame: The frame (image) to search in.
    :param threshold: The confidence threshold for a match.
    :return: A tuple (left, top, right, bottom) of the bounding box of the pattern if found, otherwise None.
    """
    if PATTERN_BIN is None:
        raise FileNotFoundError(f"Pattern image not found at {PATTERN_PATH}")

    # Convert frame to grayscale
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Binarize the frame using Otsu's thresholding to match the pattern's pre-processing
    _, frame_bin = cv2.threshold(frame_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Perform template matching on the binarized images
    res = cv2.matchTemplate(frame_bin, PATTERN_BIN, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        # The top-left corner of the matched area
        top_left = max_loc
        # Calculate the rectangle coordinates
        left = top_left[0]
        top = top_left[1]
        right = left + PATTERN_WIDTH
        bottom = top + PATTERN_HEIGHT
        return left, top, right, bottom

    return None
