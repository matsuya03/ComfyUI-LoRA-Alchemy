"""
This file is necessary to prevent ComfyUI from treating each .py file in 
this directory as an individual custom node. By providing an empty 
NODE_CLASS_MAPPINGS, ComfyUI safely imports this directory without errors.
"""

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = ""
