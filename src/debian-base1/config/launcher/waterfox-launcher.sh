#!/bin/bash
CON_ID=$(i3-msg -t get_tree | python3 -c "
import json, sys

def find_waterfox(node):
    if not node.get('nodes', []) and not node.get('floating_nodes', []):
        cls = (node.get('window_properties') or {}).get('class', '').lower()
        if 'waterfox' in cls:
            return str(node['id'])
    for child in node.get('nodes', []) + node.get('floating_nodes', []):
        result = find_waterfox(child)
        if result:
            return result
    return None

tree = json.load(sys.stdin)
print(find_waterfox(tree) or '')
" 2>/dev/null)

if [ -n "$CON_ID" ]; then
    i3-msg "[con_id=\"$CON_ID\"] focus"
else
    i3-msg '[con_mark="viewer_tabs"] focus; focus child; exec waterfox'
fi