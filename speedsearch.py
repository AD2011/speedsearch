import requests
import subprocess
import os
import sys
import threading
import time
import shutil
from prompt_toolkit import Application
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.widgets import TextArea

# Configuration
API_URL = "https://www.speedtest.net/api/js/config-sdk"

class SpeedtestCLIError(Exception):
    """Custom exception for speedtest CLI errors"""
    pass

def check_speedtest_cli():
    """
    Check if the official Ookla Speedtest CLI is installed.
    Returns True if available, False otherwise.
    """
    return shutil.which("speedtest") is not None

def check_conflicting_pip_package():
    """
    Check if the conflicting speedtest-cli pip package is installed.
    Returns True if the conflict exists, False otherwise.
    """
    try:
        import pkg_resources
        for dist in pkg_resources.working_set:
            if dist.key == 'speedtest-cli':
                return True
    except:
        pass
    return False

def handle_speedtest_cli_missing():
    """
    Prompt user with instructions to install the official Speedtest CLI.
    """
    print("\n" + "="*70)
    print("ERROR: Official Speedtest CLI is not installed")
    print("="*70)
    print("\nspeedsearch requires the official Ookla Speedtest CLI.")
    print("\nInstallation Instructions: https://www.speedtest.net/apps/cli")
    print("-" * 70)
    sys.exit(1)

def handle_conflicting_pip_package():
    """
    Prompt user to uninstall the conflicting pip package.
    """
    print("\n" + "="*70)
    print("CONFLICT: speedtest-cli pip package detected")
    print("="*70)
    print("\nA conflicting package 'speedtest-cli' from PyPI is installed.")
    print("This may cause issues with speedsearch.")
    print("\n🔧 To resolve, uninstall the conflicting package:")
    print("-" * 70)
    print("  pip uninstall speedtest-cli")
    print("-" * 70)
    response = input("\nWould you like to uninstall it now? (y/n): ").strip().lower()
    if response == 'y':
        try:
            subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "speedtest-cli"], check=True)
            print("✓ Uninstalled speedtest-cli successfully.")
            print("Please ensure the official Ookla Speedtest CLI is installed (see above).")
        except subprocess.CalledProcessError:
            print("✗ Failed to uninstall. Please try: pip uninstall speedtest-cli")
            sys.exit(1)
    else:
        print("Please resolve the conflict before continuing.")
        sys.exit(1)

class SpeedtestPrompt:
    def __init__(self):
        self.page_size = 10
        self.selected_index = 0
        self.scroll_offset = 0
        self._debounce_timer = None

        # Check for speedtest CLI
        if not check_speedtest_cli():
            handle_speedtest_cli_missing()

        # Check for conflicting pip package
        if check_conflicting_pip_package():
            handle_conflicting_pip_package()

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
        """
        Fetch servers from Speedtest API with error handling.
        """
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
            response.raise_for_status()
            data = response.json().get('servers', [])
            return data if data else []
        except requests.exceptions.Timeout:
            print("⚠️  Network timeout while fetching servers. Check your connection.")
            return []
        except requests.exceptions.ConnectionError:
            print("⚠️  Failed to connect to Speedtest API. Check your internet connection.")
            return []
        except requests.exceptions.HTTPError as e:
            print(f"⚠️  HTTP Error: {e.response.status_code}")
            return []
        except ValueError:
            print("⚠️  Invalid response from Speedtest API.")
            return []
        except Exception as e:
            print(f"⚠️  Error fetching servers: {str(e)}")
            return []

    def on_search_change(self, buffer):
        """
        Debounce logic: Cancel the previous timer and start a new one.
        Only executes fetch_servers if the user stops typing for 500ms.
        """
        if self._debounce_timer:
            self._debounce_timer.cancel()

        def do_search():
            try:
                new_results = self.fetch_servers(buffer.text)
                self.results = new_results
                self.selected_index = 0
                self.scroll_offset = 0
                # Force UI refresh from the background thread
                self.app.invalidate()
            except Exception as e:
                print(f"Search error: {str(e)}")

        self._debounce_timer = threading.Timer(0.5, do_search)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def get_menu_text(self):
        """
        Generate formatted menu text for display.
        """
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
        """
        Setup keyboard bindings for navigation and selection.
        """
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
        """
        Run the interactive server selection prompt and execute speedtest.
        """
        try:
            selected = self.app.run()
            if selected:
                # Cleanly clear the CLI prompt area
                sys.stdout.write("\033[F" * (self.page_size + 6))
                sys.stdout.write("\033[J")

                print(f"➜  Selected: {selected['sponsor']} ({selected['name']})")
                print(f"➜  Starting Speedtest...\n")
                
                try:
                    subprocess.run(["speedtest", "-s", str(selected['id'])], check=False)
                except FileNotFoundError:
                    print("❌ Error: speedtest CLI command not found.")
                    print("Please install the official Ookla Speedtest CLI from https://www.speedtest.net/apps/cli")
                    sys.exit(1)
            else:
                print("➜  Cancelled.")
        except KeyboardInterrupt:
            print("\n➜  Interrupted by user.")
            sys.exit(0)
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}")
            sys.exit(1)

def main():
    """
    Entry point for the application.
    """
    try:
        prompt = SpeedtestPrompt()
        prompt.run()
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
