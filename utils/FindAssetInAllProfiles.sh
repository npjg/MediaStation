#!/bin/bash

# This script searches all PROFILE._ST files for a given asset name
# and telsl you which profile the asset is found in (if any).

files=$(find "$1" -iname "PROFILE._ST")
search_string="$2"

while IFS= read -r file; do
    if [[ -f $file ]]; then
        grep_result=$(grep -i "$search_string" "$file")
        if [[ ! -z $grep_result ]]; then
            echo "Filename: $file"
            echo "$grep_result"
        fi
    fi
done < <(echo "$files")
