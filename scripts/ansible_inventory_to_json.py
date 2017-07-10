#!/usr/bin/env python

import argparse
import json
import os
import re
import subprocess

discard_host_strings = ['hosts']
cwd = os.path.dirname(__file__)

parser = argparse.ArgumentParser(description='Prints json mapping representing groups in Ansible inventory.')
parser.add_argument('--inventory', dest='inventory_file', help='Ansible inventory',
                    default=os.path.join(cwd, 'inventory'))
_group_filter_help = "(optional) Comma-separated list of strings. If a group's name includes one of the" \
                     "filter strings, it will be included in the results. If not specified, all " \
                     "groups are returned."
parser.add_argument('--group-filter', dest='group_filter', help=_group_filter_help, default='')
args = parser.parse_args()

group_map = dict()

# Get group names
file = open(args.inventory_file, 'r')
for line in file:
    match = re.search('\[(.*)\]', line)
    if not match or 'vars' in match.group(1):
        continue
    if args.group_filter and not any(expr in match.group(1) for expr in args.group_filter.split(',')):
        continue
    section = match.group(1)
    group_map[section] = []

    # Get hosts
    output = subprocess.check_output(['ansible', '-i', args.inventory_file, '--list-hosts', section])
    for line in output.split('\n'):
        line = line.strip()
        if len(line) and not any(expr in line for expr in discard_host_strings):
            group_map[section].append(line)

print(json.dumps(group_map))
