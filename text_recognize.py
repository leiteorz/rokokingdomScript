import cv2

try:
    import easyocr
    HAS_EASYOCR = True
    # Do not initialize the reader globally here to avoid slow startup
    reader = None
except ImportError:
    easyocr = None
    HAS_EASYOCR = False
    reader = None

def get_reader():
    global reader
    if HAS_EASYOCR and reader is None:
        # Initialize with both Chinese Simplified and English
        reader = easyocr.Reader(['ch_sim', 'en'])
    return reader

def find_text_coordinates(frame, target_text, lang='ch_sim', threshold=0.6):
    """
    Finds the bounding box of a specific target text within the given frame using EasyOCR.

    :param frame: The frame (image) to search in as a numpy array (BGR).
    :param target_text: The text string to search for.
    :param lang: Language is now ignored for the specific call since reader is initialized globally.
                 Included for backwards compatibility with function signature.
    :param threshold: Confidence threshold (0.0-1.0).
    :return: A tuple (left, top, right, bottom) of the bounding box if the text is found, otherwise None.
    """
    # Use lang parameter somehow or suppress warning if we just want backwards compatibility
    _ = lang
    
    if not HAS_EASYOCR:
        print("Error: easyocr is not installed. Please run 'pip install easyocr'.")
        return None

    ocr_reader = get_reader()
    if ocr_reader is None:
         return None

    # EasyOCR expects RGB or grayscale. OpenCV uses BGR.
    # Convert BGR to RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Use EasyOCR to read the text from the image
    # detail=1 returns bounding boxes, text, and confidence
    results = getattr(ocr_reader, 'readtext')(frame_rgb)

    target_text_lower = target_text.lower()

    # results format: [([[x1,y1], [x2,y2], [x3,y3], [x4,y4]], 'text', confidence), ...]
    for bbox, text, conf in results:
        word = text.strip()
        
        # If the detected word matches our target text (case-insensitive) and confidence is high enough
        if word and target_text_lower in word.lower() and conf >= threshold:
            # bbox is a list of 4 points: [top-left, top-right, bottom-right, bottom-left]
            # Each point is [x, y]
            top_left = bbox[0]
            bottom_right = bbox[2]
            
            left = int(top_left[0])
            top = int(top_left[1])
            right = int(bottom_right[0])
            bottom = int(bottom_right[1])
            
            return left, top, right, bottom

    return None