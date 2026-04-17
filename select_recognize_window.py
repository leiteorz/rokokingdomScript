import tkinter as tk
import time
import threading
import keyboard
import pyautogui
import random
import cv2
import numpy as np

# Attempt to import mss as an alternative to pyscreeze
try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

from focussing_energy_recognize import find_pattern
from text_recognize import find_text_coordinates

class SelectRecognizeApp:
    def __init__(self):
        self.region = None
        self.is_enabled = False
        
        self.root = tk.Tk()
        self.root.withdraw() # Hide the main root window
        
        self.overlay_win = None
        self.border_win = None
        self.status_label = None
        self.reselect_btn = None
        self.close_btn = None
        self.overlay_frame = None
        
        # Hotkeys for toggling recognition
        keyboard.add_hotkey('f10', self.enable)
        keyboard.add_hotkey('f11', self.disable)
        
        # Start background thread for the recognition loop
        self.recognize_thread = threading.Thread(target=self.recognition_loop, daemon=True)
        self.recognize_thread.start()
        
        # Start status update loop
        self.update_status_loop()
        
        # Schedule first selection to allow the mainloop to start properly
        self.root.after(100, lambda: self.do_reselect())
        
        self.root.mainloop()

    def do_reselect(self):
        self.is_enabled = False
        if self.overlay_win:
            self.overlay_win.destroy()
            self.overlay_win = None
        if self.border_win:
            self.border_win.destroy()
            self.border_win = None
            
        self.region = None
        print("Please drag to select the recognition area. Press ESC to cancel.")
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
            sel_win.destroy()
            if not self.region:
                self.root.quit()

        sel_win.bind("<Escape>", on_escape)

    def on_region_selected(self):
        if self.region:
            print(f"Region selected: {self.region}")
            self.setup_border()
            self.setup_overlay()
            print("Press F10 to Start, F11 to Stop.")
        else:
            print("Selection cancelled.")
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
        if self.region:
            self.is_enabled = True
            print("Recognition Enabled")

    def disable(self):
        self.is_enabled = False
        print("Recognition Disabled")

    @staticmethod
    def get_screenshot_mss(x1, y1, x2, y2):
        # We know mss is imported here if HAS_MSS is True
        import mss as mss_lib
        with mss_lib.mss() as sct:
            monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
            img = sct.grab(monitor)
            # Convert to numpy array in BGR format
            return np.array(img)[:, :, :3]

    def perform_click(self, x1, y1, match_rect, label):
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
        print(f"{label} found! Clicked inside rect at ({click_x}, {click_y})")

    def recognition_loop(self):
        while True:
            if self.is_enabled and self.region:
                x1, y1, x2, y2 = self.region
                width = x2 - x1
                height = y2 - y1
                try:
                    if HAS_MSS:
                        frame = self.get_screenshot_mss(x1, y1, x2, y2)
                    else:
                        # Fallback to pyautogui if mss is not installed. 
                        screenshot = pyautogui.screenshot(region=(x1, y1, width, height))
                        frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                    
                    # 1. Search for the target pattern
                    pattern_rect = find_pattern(frame)
                    if pattern_rect:
                        self.perform_click(x1, y1, pattern_rect, "Pattern")
                    
                    # 2. Search for the text "带带你"
                    # Pass lang='chi_sim' specifically as "带带你" is Chinese.
                    text_rect = find_text_coordinates(frame, "带带你", lang='chi_sim')
                    if text_rect:
                        self.perform_click(x1, y1, text_rect, "Text '带带你'")

                except Exception as e:
                    print(f"Error during recognition: {e}")
            
            # Wait for 1 second before capturing the next frame
            time.sleep(1)

if __name__ == "__main__":
    SelectRecognizeApp()