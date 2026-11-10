"""Live adapter: official Upwork MCP server (https://mcp.upwork.com/mcp, OAuth 2.1).

TODO (Part A4): connect with MultiServerMCPClient over Streamable HTTP, complete OAuth,
store tokens encrypted per user, and map Upwork tools onto the MarketplacePort methods.
Rules: proposals/messages are created only as DRAFTS that the user confirms on Upwork;
no scraping, no browser automation, conservative polling interval.
"""


class UpworkLiveAdapter:
    def __init__(self):
        raise NotImplementedError("Live Upwork mode is not implemented yet. Use MARKETPLACE_MODE=gigsim.")
