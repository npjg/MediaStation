#!/usr/bin/python3

import logging
import argparse
import mmap

import cxt

def main(inp, start, end): 
    with open(inp, mode='rb') as f:
        stream = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)
        stream.seek(start)

        if not end: end = cxt.read_chunk(stream)["size"] + start + 0x04
        print("---- START OF DUMP ----")
        while stream.tell() < end:
            print(cxt.Datum(stream))

        print("---- END OF DUMP ----")

# Nifty trick:
# https://stackoverflow.com/questions/25513043/python-argparse-fails-to-parse-hex-formatting-to-int-type
def auto_int(x):
    return int(x, 0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="ddump", description="Dump low-level data from Media Station, Inc. games"
    )

    parser.add_argument(
        "input", help="Pass a context (CXT) filename to process the file."
    )

    parser.add_argument(
        "-c", "--chunk", default=None, nargs=1, type=auto_int,
        help="Pass the starting address of a chunk here to parse all datums in the chunk."
    )

    parser.add_argument(
        "-a", "--addrs", default=None, nargs=2, type=auto_int,
        help="Manually set the starting and ending addresses to parse. The ending address will be aligned up to inclue a full datum at the end."
    )

    logging.basicConfig(level=logging.DEBUG)
    args = parser.parse_args()

    if args.chunk and args.addrs:
        raise argparse.ArgumentTypeError("Conflict between chunk and address spefifications. Please supply only one.")
    elif not args.chunk and not args.addrs:
        raise argparse.ArgumentTypeError("At least one of the chunk or address spefifications must be supplied.")
    elif args.chunk:
        main(args.input, args.chunk[0], None)
    elif args.addrs:
        logging.info("When using manual address mode, make sure the start address is on a datum boundary or strange parser errors will result!")
        main(args.input, *args.addrs)

