#!/usr/bin/python3

import argparse
import os
import logging

import cxt

def main(directory):
    results = {}

    for entry in os.listdir(directory):
        if entry.endswith("cxt"):
            logging.info("Opened context {}".format(entry))
            try:
                cxt.main(os.path.join(directory, entry))
                result = "Pass"
            except Exception as e:
                result = e

            results.update({entry: result})
            print()

    print(results)

logging.basicConfig(level=logging.DEBUG)

parser = argparse.ArgumentParser(prog="test")
parser.add_argument("input")

args = parser.parse_args()
main(args.input)

