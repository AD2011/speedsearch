import requests
import subprocess
import os
import sys
import threading
import time
from prompt_toolkit import Application
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.widgets import TextArea

# Configuration
API_URL = "https://www.speedtest.net/api/js/config-sdk"

class SpeedtestPrompt:
    def __init__(self):
        self.page_size = 10
        self.selected_index = 0
        self.scroll_offset = 0
        self._debounce_timer = None

        # 1. Fetch initial default servers
        self.results = self.fetch_servers("")

        # Input Field
        self.search_field = TextArea(
            prompt="│  Search: ",
            multiline=False,
        )
        self.search_field.buffer.on_text_changed += self.on_search_change

        # Results Display Control
        self.results_control = FormattedTextControl(self.get_menu_text)

        # Layout
        layout_container = HSplit([
            Window(content=FormattedTextControl("┌  Speedtest CLI"), height=1),
            Window(content=FormattedTextControl("│"), height=1),
            Window(content=FormattedTextControl("◆  Select Server"), height=1),
            self.search_field,
            Window(content=self.results_control, height=self.page_size),
            Window(content=FormattedTextControl("│  ↑/↓: navigate • Enter: select • Esc: cancel"), height=1)
        ])

        self.kb = KeyBindings()
        self.setup_bindings()

        self.app = Application(
            layout=Layout(layout_container, focused_element=self.search_field),
            key_bindings=self.kb,
            erase_when_done=True,
        )

    def fetch_servers(self, query):
        limit = 10 if not query else 50
        params = {
            'engine': 'js',
            'search': query,
            'https_functional': 'true',
            'limit': limit
        }
        try:
            if not query:
                del params['search']
            response = requests.get(API_URL, params=params, timeout=5)
            return response.json().get('servers', [])
        except:
            return []

    def on_search_change(self, buffer):
        """
        Debounce logic: Cancel the previous timer and start a new one.
        Only executes fetch_servers if the user stops typing for 500ms.
        """
        if self._debounce_timer:
            self._debounce_timer.cancel()

        def do_search():
            new_results = self.fetch_servers(buffer.text)
            self.results = new_results
            self.selected_index = 0
            self.scroll_offset = 0
            # Force UI refresh from the background thread
            self.app.invalidate()

        self._debounce_timer = threading.Timer(0.5, do_search)
        self._debounce_timer.start()

    def get_menu_text(self):
        if not self.results:
            return [("", "│  (Searching...)")]

        formatted_lines = []
        visible_chunk = self.results[self.scroll_offset : self.scroll_offset + self.page_size]

        for i, server in enumerate(visible_chunk):
            idx = i + self.scroll_offset
            marker = "●" if idx == self.selected_index else "○"

            sponsor = server.get('sponsor', 'Unknown')
            city = server.get('name', 'Unknown')
            sid = server.get('id', 'N/A')

            label = f"│  {marker} {sponsor} ({city}) [{sid}]"

            if idx == self.selected_index:
                formatted_lines.append(("ansicyan bold", label + "\n"))
            else:
                formatted_lines.append(("", label + "\n"))

        return formatted_lines

    def setup_bindings(self):
        @self.kb.add('up')
        def _(event):
            if self.selected_index > 0:
                self.selected_index -= 1
                if self.selected_index < self.scroll_offset:
                    self.scroll_offset -= 1

        @self.kb.add('down')
        def _(event):
            if self.selected_index < len(self.results) - 1:
                self.selected_index += 1
                if self.selected_index >= self.scroll_offset + self.page_size:
                    self.scroll_offset += 1

        @self.kb.add('enter')
        def _(event):
            if self.results:
                # Cancel any pending search if user hits enter immediately
                if self._debounce_timer:
                    self._debounce_timer.cancel()
                self.app.exit(result=self.results[self.selected_index])

        @self.kb.add('escape')
        @self.kb.add('c-c')
        def _(event):
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self.app.exit()

    def run(self):
        selected = self.app.run()
        if selected:
            # Cleanly clear the CLI prompt area
            sys.stdout.write("\033[F" * (self.page_size + 6))
            sys.stdout.write("\033[J")

            print(f"➜  Selected: {selected['sponsor']} ({selected['name']})")
            print(f"➜  Starting Speedtest...\n")
            subprocess.run(["speedtest", "-s", str(selected['id'])])
        else:
            print("➜  Cancelled.")

if __name__ == "__main__":
    SpeedtestPrompt().run()
