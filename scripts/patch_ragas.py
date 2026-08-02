#!/usr/bin/env python3
"""Patch ragas to use new langchain_google_vertexai import location."""
import re

file_path = '/usr/local/lib/python3.12/site-packages/ragas/llms/base.py'

with open(file_path, 'r') as f:
    content = f.read()

# Replace the import block
old_import = """import instructor
from langchain_community.chat_models.vertexai import ChatVertexAI
from langchain_community.llms import VertexAI"""

new_import = """import instructor
try:
    from langchain_google_vertexai import ChatVertexAI, VertexAI
except ImportError:
    from langchain_community.chat_models.vertexai import ChatVertexAI
    from langchain_community.llms import VertexAI"""

content = content.replace(old_import, new_import)

with open(file_path, 'w') as f:
    f.write(content)

print("Patched ragas successfully")