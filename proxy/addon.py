"""
Templeton harness proxy — mitmproxy addon entry point.

Phase 0: skeleton that loads without errors.
Phase 4: bang enforcement, response inspection, live report assembly.
"""

import mitmproxy.http


class TempletonAddon:
    def request(self, flow: mitmproxy.http.HTTPFlow) -> None:
        pass

    def response(self, flow: mitmproxy.http.HTTPFlow) -> None:
        pass


addons = [TempletonAddon()]
