import tkinter as tk
from tkinter import ttk
import time
import threading
import keyboard
import pyautogui
import random
import cv2
import numpy as np
import ctypes
import logging
import sys
import queue

# Move heavy imports away from the top level
# These can significantly slow down PyInstaller executables
# import mss
# from focussing_energy_recognize import find_pattern, get_pattern
# from text_recognize import find_text_coordinates, get_reader

# Setup logging without file handler
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Fix Windows DPI scaling issues so tkinter coordinates match actual screen pixels
try:
    # Windows 8.1+
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception as e:
    logging.debug(f"SetProcessDpiAwareness failed: {e}")
    try:
        # Windows Vista+
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception as e2:
        logging.debug(f"SetProcessDPIAware failed: {e2}")

class SelectRecognizeApp:
    def __init__(self):
        self.region = None
        self.is_enabled = False
        self.is_loading = True
        self.modules_loaded = False
        
        self.has_mss = False
        
        # Caches to restrict the search region after first detection
        self.cached_pattern_rect = None
        # We are intentionally removing the text cache per user request
        
        # Initialize Tkinter immediately to show UI fast
        self.root = tk.Tk()
        self.root.title("RokoKingdom Script") # Added title
        
        # Ensure the root window itself is not completely unmanaged
        # In tkinter, `withdraw()` hides the window from the taskbar too.
        # Instead of `withdraw()`, we use `iconify()` or hide it by moving it off-screen,
        # but to keep it in the taskbar, the main window needs to exist.
        
        # Let's create a minimal visible main window that holds the taskbar icon
        self.root.geometry("250x150")
        self.root.minsize(250, 150)
        # Position it somewhere unobtrusive or just let it be a control panel
        tk.Label(self.root, text="RokoKingdom Script\n\nF10 to Start\nF11 to Stop", font=("Arial", 10)).pack(expand=True, fill="both")
        
        self.overlay_win = None
        self.border_win = None
        self.status_label = None
        self.reselect_btn = None
        self.close_btn = None
        self.overlay_frame = None
        self.loading_label = None
        
        # We will use this to communicate when loading is done
        self.loading_queue = queue.Queue()
        
        # Hotkeys for toggling recognition
        keyboard.add_hotkey('f10', self.enable)
        keyboard.add_hotkey('f11', self.disable)
        
        # Show loading screen FIRST before starting any threads
        self.show_loading_screen()
        
        # Start a thread to load heavy modules in the background
        threading.Thread(target=self.load_modules_background, daemon=True).start()
        
        # Start background threads for the recognition loops
        self.pattern_thread = threading.Thread(target=self.pattern_recognition_loop, daemon=True)
        self.pattern_thread.start()
        
        self.text_thread = threading.Thread(target=self.text_recognition_loop, daemon=True)
        self.text_thread.start()
        
        # Start status update loop
        self.update_status_loop()
        
        logging.info("Application started. Waiting for modules to load...")
        self.root.mainloop()

    def load_modules_background(self):
        """Loads heavy OCR and CV models in the background"""
        try:
            logging.info("Starting background loading of AI models...")
            
            # 1. Import mss
            try:
                global mss
                import mss
                self.has_mss = True
            except ImportError:
                self.has_mss = False
                logging.warning("mss module not found. Falling back to pyautogui screenshot.")

            # 2. Import the heavy modules locally here
            global find_pattern, find_text_coordinates, get_reader, get_pattern
            from focussing_energy_recognize import find_pattern, get_pattern
            from text_recognize import find_text_coordinates, get_reader
            
            # 3. Force initialization of the OCR and Image caches
            get_pattern()
            get_reader()
            
            logging.info("AI models loaded successfully!")
            self.modules_loaded = True
            self.loading_queue.put("DONE")
            
        except Exception as e:
            logging.error(f"Failed to load modules: {e}", exc_info=True)
            self.loading_queue.put("ERROR")

    def show_loading_screen(self):
        self.loading_win = tk.Toplevel(self.root)
        self.loading_win.title("Loading...")
        
        # Center the window
        window_width = 300
        window_height = 100
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        
        self.loading_win.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        self.loading_win.overrideredirect(True) # Remove border
        self.loading_win.attributes("-topmost", True)
        
        frame = tk.Frame(self.loading_win, bg="white", highlightbackground="black", highlightthickness=1)
        frame.pack(fill="both", expand=True)
        
        tk.Label(frame, text="Initializing AI Models...", font=("Arial", 12, "bold"), bg="white").pack(pady=(20, 10))
        
        # Progress bar animation
        self.progress = ttk.Progressbar(frame, mode='indeterminate', length=200)
        self.progress.pack(pady=5)
        self.progress.start(10)
        
        # Check loading status periodically
        self.check_loading_status()

    def check_loading_status(self):
        try:
            msg = self.loading_queue.get_nowait()
            if msg == "DONE":
                self.progress.stop()
                self.loading_win.destroy()
                self.is_loading = False
                # Proceed to area selection
                self.do_reselect()
            else:
                # Handle error case
                tk.Label(self.loading_win, text="Failed to load models. Check console.", fg="red").pack()
        except queue.Empty:
            # Not done yet, check again in 100ms
            self.root.after(100, self.check_loading_status)

    def do_reselect(self):
        if self.is_loading:
            return
            
        self.is_enabled = False
        if self.overlay_win:
            self.overlay_win.destroy()
            self.overlay_win = None
        if self.border_win:
            self.border_win.destroy()
            self.border_win = None
            
        self.region = None
        # Clear caches upon reselecting the screen area
        self.cached_pattern_rect = None
        
        logging.info("Please drag to select the recognition area. Press ESC to cancel.")
        self.select_region()

    def select_region(self):
        sel_win = tk.Toplevel(self.root)
        sel_win.attributes('-alpha', 0.3)
        sel_win.attributes('-fullscreen', True)
        sel_win.attributes('-topmost', True)
        sel_win.config(cursor="cross")

        canvas = tk.Canvas(sel_win, cursor="cross", bg="gray")
        canvas.pack(fill="both", expand=True)

        start_x = 0
        start_y = 0
        rect = 0
        dragging = False

        def on_press(event):
            nonlocal start_x, start_y, rect, dragging
            start_x, start_y = event.x, event.y
            dragging = True
            rect = canvas.create_rectangle(start_x, start_y, start_x, start_y, outline='red', width=3)

        def on_drag(event):
            nonlocal rect, dragging
            if dragging and rect != 0:
                canvas.coords(rect, start_x, start_y, event.x, event.y)

        def on_release(event):
            nonlocal start_x, start_y, dragging
            end_x, end_y = event.x, event.y
            dragging = False
            
            x1, x2 = min(start_x, end_x), max(start_x, end_x)
            y1, y2 = min(start_y, end_y), max(start_y, end_y)
            
            # Ensure the selected area is valid (at least 10x10)
            if x2 - x1 > 10 and y2 - y1 > 10:
                self.region = (x1, y1, x2, y2)
                
            sel_win.destroy()
            self.on_region_selected()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

        def on_escape(event):
            # The event argument is provided by tkinter but we don't need its value
            _ = event
            sel_win.destroy()
            if not self.region:
                logging.info("Selection cancelled, exiting.")
                self.root.quit()

        sel_win.bind("<Escape>", on_escape)

    def on_region_selected(self):
        if self.region:
            logging.info(f"Region selected: {self.region}")
            self.setup_border()
            self.setup_overlay()
            logging.info("Press F10 to Start, F11 to Stop.")
        else:
            logging.info("Selection cancelled.")
            self.root.quit()

    def setup_border(self):
        self.border_win = tk.Toplevel(self.root)
        x1, y1, x2, y2 = self.region
        
        # Expand the border slightly outwards so it is NOT captured inside the screenshot 
        bx1, by1 = x1 - 2, y1 - 2
        border_width = (x2 - x1) + 4
        border_height = (y2 - y1) + 4
        
        self.border_win.geometry(f"{border_width}x{border_height}+{bx1}+{by1}")
        self.border_win.overrideredirect(True)
        self.border_win.attributes("-topmost", True)
        
        # Use a transparent background for Windows so only the red frame shows
        self.border_win.attributes("-transparentcolor", "fuchsia")
        self.border_win.config(bg="fuchsia")
        
        canvas = tk.Canvas(self.border_win, bg="fuchsia", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        
        # Draw the red border outline
        canvas.create_rectangle(0, 0, border_width-1, border_height-1, outline="red", width=2)

        # Add close button in the top-left corner
        self.close_btn = tk.Button(self.border_win, text="关闭", command=self.root.quit, font=("Arial", 9), bg="#ff4d4d", fg="white", relief="flat")
        self.close_btn.place(x=0, y=0)

    def setup_overlay(self):
        self.overlay_win = tk.Toplevel(self.root)
        x1, y1, x2, y2 = self.region
        
        width = 160
        height = 30
        
        # Position in the top-right corner of the selected area
        pos_x = x2 - width
        pos_y = y1
        self.overlay_win.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        self.overlay_win.overrideredirect(True)
        self.overlay_win.attributes("-topmost", True)
        
        # Using a Frame to hold both label and button to avoid overlap
        self.overlay_frame = tk.Frame(self.overlay_win, bg="white")
        self.overlay_frame.pack(fill="both", expand=True)
        
        self.status_label = tk.Label(self.overlay_frame, text="已停止", fg="red", bg="white", font=("Arial", 10, "bold"))
        self.status_label.pack(side="left", fill="both", expand=True)
        
        self.reselect_btn = tk.Button(self.overlay_frame, text="重新选择", command=self.do_reselect, font=("Arial", 9), relief="flat", bg="#e0e0e0")
        self.reselect_btn.pack(side="right", fill="y", padx=2, pady=2)
        
    def update_status_loop(self):
        if self.overlay_win and self.overlay_win.winfo_exists() and self.status_label:
            if self.is_enabled:
                self.status_label.config(text="运行中", fg="green")
                # Hide the reselect button when the script is enabled
                if self.reselect_btn and self.reselect_btn.winfo_ismapped():
                    self.reselect_btn.pack_forget()
            else:
                self.status_label.config(text="已停止", fg="red")
                # Show the reselect button when disabled
                if self.reselect_btn and not self.reselect_btn.winfo_ismapped():
                    self.reselect_btn.pack(side="right", fill="y", padx=2, pady=2)
                    
        # Refresh every 200 ms
        self.root.after(200, lambda: self.update_status_loop())

    def enable(self):
        if self.region and self.modules_loaded:
            self.is_enabled = True
            logging.info("Recognition Enabled")

    def disable(self):
        self.is_enabled = False
        logging.info("Recognition Disabled")

    def get_screenshot_mss(self, x1, y1, x2, y2):
        # We know mss is imported here if self.has_mss is True
        with mss.mss() as sct:
            monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
            img = sct.grab(monitor)
            # Convert to numpy array in BGR format
            return np.array(img)[:, :, :3]

    @staticmethod
    def perform_click(x1, y1, match_rect, label):
        match_left, match_top, match_right, match_bottom = match_rect
                        
        # Translate the matched coordinates relative to the full screen
        abs_left = x1 + match_left
        abs_top = y1 + match_top
        abs_right = x1 + match_right
        abs_bottom = y1 + match_bottom
        
        # Randomize a click coordinate inside the bounding box
        click_x = random.randint(abs_left, abs_right)
        click_y = random.randint(abs_top, abs_bottom)
        
        # Execute the mouse click
        pyautogui.click(x=click_x, y=click_y)
        logging.info(f"{label} found! Clicked inside rect at ({click_x}, {click_y})")

    def _run_cached_recognition(self, x1, y1, x2, y2, cached_rect, search_func, label, padding=50):
        """
        Helper method to grab a smaller screen region using the cached bounding box,
        padding it slightly to account for minor movements, and perform recognition.
        If it fails, it returns False so the caller can fall back to a full-region search.
        """
        c_left, c_top, c_right, c_bottom = cached_rect
        
        # Create a bounding box around the previous match with some padding
        # Constrain it to the boundaries of the original selected region
        search_x1 = max(0, c_left - padding)
        search_y1 = max(0, c_top - padding)
        search_x2 = min(x2 - x1, c_right + padding)
        search_y2 = min(y2 - y1, c_bottom + padding)
        
        abs_search_x1 = x1 + search_x1
        abs_search_y1 = y1 + search_y1
        abs_search_x2 = x1 + search_x2
        abs_search_y2 = y1 + search_y2
        
        if self.has_mss:
            frame = self.get_screenshot_mss(abs_search_x1, abs_search_y1, abs_search_x2, abs_search_y2)
        else:
            screenshot = pyautogui.screenshot(region=(abs_search_x1, abs_search_y1, abs_search_x2 - abs_search_x1, abs_search_y2 - abs_search_y1))
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

        # Run the specific search function
        match_rect = search_func(frame)
        
        if match_rect:
            # The coordinates returned are relative to the padded search box.
            # We must convert them back to be relative to the original full region (x1, y1)
            # so `perform_click` and the cache can work seamlessly.
            m_left, m_top, m_right, m_bottom = match_rect
            
            rel_to_region_left = search_x1 + m_left
            rel_to_region_top = search_y1 + m_top
            rel_to_region_right = search_x1 + m_right
            rel_to_region_bottom = search_y1 + m_bottom
            
            adjusted_rect = (rel_to_region_left, rel_to_region_top, rel_to_region_right, rel_to_region_bottom)
            self.perform_click(x1, y1, adjusted_rect, label)
            return adjusted_rect
            
        return None

    def pattern_recognition_loop(self):
        while True:
            if self.is_enabled and self.region and self.modules_loaded:
                x1, y1, x2, y2 = self.region
                width = x2 - x1
                height = y2 - y1
                
                try:
                    # 1. Search for the target pattern
                    pattern_found_in_cache = False
                    if self.cached_pattern_rect:
                        # Try searching in the cached sub-region first
                        new_rect = self._run_cached_recognition(
                            x1, y1, x2, y2, self.cached_pattern_rect, 
                            lambda f: find_pattern(f), "Pattern (Cached)"
                        )
                        if new_rect:
                            self.cached_pattern_rect = new_rect
                            pattern_found_in_cache = True
                        else:
                            # If it moved outside the padded box or disappeared, invalidate the cache
                            logging.info("Pattern cache invalidated.")
                            self.cached_pattern_rect = None

                    if not pattern_found_in_cache:
                        # Fallback to full region search
                        if self.has_mss:
                            full_frame = self.get_screenshot_mss(x1, y1, x2, y2)
                        else:
                            screenshot = pyautogui.screenshot(region=(x1, y1, width, height))
                            full_frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                            
                        pattern_rect = find_pattern(full_frame)
                        if pattern_rect:
                            self.perform_click(x1, y1, pattern_rect, "Pattern")
                            self.cached_pattern_rect = pattern_rect

                except Exception as err:
                    logging.error(f"Error during pattern recognition: {err}", exc_info=True)
            
            # Wait for 1 second before capturing the next frame
            time.sleep(1)

    def text_recognition_loop(self):
        while True:
            if self.is_enabled and self.region and self.modules_loaded:
                x1, y1, x2, y2 = self.region
                width = x2 - x1
                height = y2 - y1
                
                try:
                    # 2. Search for the text "带带你"
                    # We only process the central third of the image to optimize performance
                    third_width = width // 3
                    
                    # Instead of grabbing the full frame, we can grab only the central third
                    # Calculate central third coordinates
                    cx1 = x1 + third_width
                    cx2 = x1 + 2 * third_width
                    c_width = cx2 - cx1
                    
                    if self.has_mss:
                        central_frame = self.get_screenshot_mss(cx1, y1, cx2, y2)
                    else:
                        screenshot = pyautogui.screenshot(region=(cx1, y1, c_width, height))
                        central_frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                        
                    text_rect = find_text_coordinates(central_frame, "带带你", lang='ch_sim')
                    if text_rect:
                        # text_rect will be relative to central_frame. We need to shift it horizontally
                        left, top, right, bottom = text_rect
                        adjusted_rect = (left + third_width, top, right + third_width, bottom)
                        self.perform_click(x1, y1, adjusted_rect, "Text '带带你'")

                except Exception as err:
                    logging.error(f"Error during text recognition: {err}", exc_info=True)
            
            # Wait for 1 second before capturing the next frame
            time.sleep(1)

if __name__ == "__main__":
    SelectRecognizeApp()