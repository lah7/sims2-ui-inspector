"""
Shared state of the application
"""
from sims2patcher import dbpf


class State:
    """A collection of entries from a .package file"""
    file_list: list[str] = [] # List of paths
    graphics: dict[tuple, dbpf.Entry] = {} # (group_id, instance_id) -> Entry
