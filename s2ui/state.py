"""
Shared state of the application
"""
from sims2patcher import dbpf


class State:
    """
    Global state for the application. References of the files for the
    currently opened package(s), and the current item being viewed.
    """
    file_list: list[str] = [] # List of paths
    graphics: dict[tuple, dbpf.Entry] = {} # (group_id, instance_id) -> Entry

    current_group_id = 0x0
    current_instance_id = 0x0
