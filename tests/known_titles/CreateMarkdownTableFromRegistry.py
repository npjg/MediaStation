#!/usr/bin/env python
# This script takes the JSON file that keeps all known Media Station titles.
# and formats it in a format for presentation on the Wiki. 
# (https://github.com/npjg/MediaStation/wiki/All-Known-Media-Station-Titles).
# Currently only this one-way synchronization is supported - going from the wiki back to the JSON is not supported yet.
# This script MUST be run from the root directory of this repository.
import json
import re

def remove_comments(jsonc_string):
    # Regular expression to match single-line comments (//)
    single_line_comment_regex = re.compile(r'//.*$', re.MULTILINE)
    # Regular expression to match multi-line comments (/* ... */)
    multi_line_comment_regex = re.compile(r'/\*.*?\*/', re.DOTALL)

    # Remove both single-line and multi-line comments
    no_comments_string = re.sub(single_line_comment_regex, '', jsonc_string)
    no_comments_string = re.sub(multi_line_comment_regex, '', no_comments_string)

    return no_comments_string

def CreateMarkdownTable(data):
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

def CreateEasyList(data):
    full_names = []
    for entry in data:
        if entry['full_name'] not in full_names:
            if entry['publisher'] is not None:
                print(f"- {entry['full_name']} - {entry['publisher']} ({entry['date']})")
            else:
                print(f"- {entry['full_name']} ({entry['date']})")

        full_names.append(entry['full_name'])

if __name__ == "__main__":
    with open('tests/known_titles/registry.jsonc', 'rb') as f:
        # REMOVE COMMENTS FROM THE JSON.
        jsonc_string = f.read().decode('utf-8')
        json_string = remove_comments(jsonc_string)

        # LOAD THE DATA FROM THE JSON.
        data = json.loads(json_string)
        for entry in data:
            if 'date' in entry:
                date = entry['date']
                if isinstance(date, str):
                    # Check if the date is in the format "YYYY-MM-DD"
                    if re.match(r'\d{2}/\d{2}/\d{4}', date):
                        entry['date'] = date[6:]  # Extract the year
                    elif len(date) == 4:
                        # Assume the date is already in the format "YYYY"
                        entry['date'] = date
                    else:
                        raise ValueError(f"Invalid date format: {date}")

        data = sorted(data, key = lambda x: x['date'])
        # The JSON has other fields, but only these fields are valuable to report
        # on the wiki. Specifying this order also lets us put the most important information up front.
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

        print('*** EASY LIST ***')
        CreateEasyList(data)
        print('** MARKDOWN TABLE **')
        CreateMarkdownTable(data)
