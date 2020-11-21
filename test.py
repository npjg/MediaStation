#!/usr/bin/python3

import argparse
import os
import logging

import cxt

def main(directory, string):
    results = {}

    for entry in os.listdir(directory):
        if entry.endswith("cxt") and entry.split('.')[0].isnumeric():
            logging.info("Opened context {}".format(entry))
            try:
                cxt.main(os.path.join(directory, entry), string)
                result = "Pass"
            except Exception as e:
                result = e
                raise

            results.update({entry: result})
            print()

    print(results)

logging.basicConfig(level=logging.DEBUG)

parser = argparse.ArgumentParser(prog="test")
parser.add_argument("input")
parser.add_argument("--string", default=False, action='store_true', help="Parse contexts with debug strings")

args = parser.parse_args()
main(args.input, args.string)

