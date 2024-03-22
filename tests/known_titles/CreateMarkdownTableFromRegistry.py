#!/usr/bin/env python
import json

# This script takes the JSON file that keeps all known Media Station titles
# and formats it in a format for presentation on the wiki 
# (https://github.com/npjg/MediaStation/wiki/All-Known-Media-Station-Titles).
# Currently only this one-way synchronization is supported - going from the wiki back to 
# the JSON is not supported yet.

with open('registry.json', 'rb') as f:
    # LOAD THE DATA FROM THE JSON.
    data = json.load(f)
    data = sorted(data, key = lambda x: x['date'])
    # The JSON has other headers, but only these are valuable to report
    # on the wiki. Specifying this order also lets us put the most important
    # information up front.
    headers = [
        "full_name",
        "have_cdrom",
        "publisher",
        "date",
        "platforms",
        "language",
        "engine_version",
        "title_compiler_version",
        "profile_version",
        "source_url"
    ]
    # If you wanted to calculate the headers automatically, you 
    # would do this instead.
    #
    # headers = set()
    # for entry in data:
    #     headers.update(entry.keys())
    # # We would never want to show the 'files' list, which will just be 
    # a list of hashes.
    # headers.discard('files')  # Exclude 'files' from headers
    # headers = sorted(list(headers))

    # WRITE THE MARKDOWN TABLE BODY HEADER.
    markdown_table = '| ' + ' | '.join(headers) + ' |\n'
    markdown_table += '|-' + '-|-'.join(['' for _ in headers]) + '-|\n'

    # WRITE THE MARKDOWN TABLE BODY.
    for entry in data:
        row = []
        for header in headers:
            if header in entry:
                cell = entry[header]
                if isinstance(cell, list):
                    row.append(', '.join(cell))

                elif cell == True:
                    row.append('✅')

                elif cell == False:
                    row.append('❌')

                elif cell is None:
                    row.append(' - ')

                else:
                    row.append(str(cell))

            else:
                # Just ignore fields that we didn't specify in the headers.
                row.append('')
        markdown_table += '| ' + ' | '.join(row) + ' |\n'

    print(markdown_table)
