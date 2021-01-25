#!/usr/bin/python3

import logging
import argparse
import mmap
import traceback

import cxt

def main(inp, start, end=None): 
    with open(inp, mode='rb') as f:
        stream = mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ)
        stream.seek(start)

        if not end: end = cxt.read_chunk(stream)["size"] + start + 0x04
        print("---- START OF DUMP ----")

        i = 0
        pause = False
        prev = None

        while stream.tell() < end:
            try:
                datum = cxt.Datum(stream)
                if i == 3 and datum.d == cxt.AssetType.STG:
                    logging.info("Detected stage chunk; enabled automatic pausing on each asset")
                    pause = True

                if pause and datum.d == cxt.HeaderType.ASSET and prev.d == 0:
                    input("Press any key to continue...")

                print(datum)
            except Exception as e:
                traceback.print_exc()
                stream.read(int(input("Bytes to skip? "), 0))

            i += 1
            prev = datum

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
        "range", nargs='+', type=auto_int,
        help="The address range to dump. If only one address is provided, it is treated as the start of an IFF chunk."
    )


    # logging.basicConfig(level=logging.DEBUG)
    args = parser.parse_args()

    if len(args.range) == 2:
        logging.info("When using manual address mode, make sure the start address is on a datum boundary or strange parser errors will result!")
    elif len(args.range) > 2:
        raise argparse.ArgumentTypeError("More than two range addresses specified")

    main(args.input, *args.range)

