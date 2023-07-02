#!/usr/bin/python3

## This program extracts asets from Media Station titles. Refer to the readme 
## for information on tested titles and known issues.
## Overall Design:
##  - Some of the data structures used in the files are rather strange and suited 
##    for real-time playback instead of asset extraction. So first all the data is
##    read from the files. Each structure in the data files generally has its own
##    class in this application, and structures that correspond to multimedia assets 
##    also support exporting. There is a little bit of inconsistency as to what
##    constitutes a "structure" here as opposed to just a piece of another structure.
##    But the arrangement I have adopted has seemed to preserve conceptual integrity 
##    pretty well.
##  - Each of the classes populated from the data is generally exported to JSON.
##  - Multimedia files are exported to BMP or WAV.

from asset_extraction_framework.CommandLine import CommandLineArguments
from asset_extraction_framework.Application import Application, FileDetectionEntry

from MediaStation import global_variables 
from MediaStation.System import System
from MediaStation.Context import Context
from MediaStation.Profile import Profile

class MediaStationEngine(Application):
    def __init__(self, application_name: str):
        super().__init__(application_name)

    ## Verifies that the asstes listed in the BOOT.STM file are exactly the ones
    ## that are actually present in the CXT files. Requires at least one BOOT.STM
    ## file and 
    def check_integrity(self):
        pass

    ## Gets an asset with associated data chunk(s) by the FourCC for those chunk(s).
    ## Usually assets are defined in the same context that has their data, so this 
    ## is not necessary. However, some new-generation titles have INSTALL.CXT files,
    ## intended to be copied to the hard drive, that only contain asset data chunks
    ## and no asset headers. So this application-level lookup is necessary to correctly
    ## link up the data in this file with the asset headers.
    def get_asset_by_chunk_id(self, chunk_id: str):
        for file in self.files:
            if file.extension.lower() == 'cxt':
                found_asset = file.get_asset_by_chunk_id(chunk_id)
                if found_asset is not None:
                    return (file, found_asset)

def main():
    # DEFINE THE FILE TYPES IN THIS APPLICATION.
    file_detection_entries = [
        FileDetectionEntry(filename_regex = '.*\.stm$', case_sensitive = False, file_processor = System),
        # All regular context files have only digits in their main file names. 
        FileDetectionEntry(filename_regex = '\d+\.cxt$', case_sensitive = False, file_processor = Context),
        # The INSTALL.CXT, if present, MUST be read after all the other contexts are read. This is because 
        # INSTALL.CXT contains no asset headers; it jumps directly into the asset subfiles. So if the asset
        # headers have not all been read, an error will be thrown. It is much simpler to just force INSTALL.CXT
        # to be read afterward than let asset subfiles be read before the headers.
        FileDetectionEntry(filename_regex = 'install.cxt$', case_sensitive = False, file_processor = Context),
        FileDetectionEntry(filename_regex = 'profile._st$', case_sensitive = False, file_processor = Profile),
    ]

    # PARSE THE COMMAND-LINE ARGUMENTS.
    APPLICATION_NAME = 'Media Station'
    APPLICATION_DESCRIPTION = ''
    command_line_arguments = CommandLineArguments(APPLICATION_NAME, APPLICATION_DESCRIPTION).parse()

    # PARSE THE ASSETS.
    media_station_engine = MediaStationEngine(APPLICATION_NAME)
    global_variables.application = media_station_engine
    media_station_engine.process(command_line_arguments.input, file_detection_entries)

    # EXPORT THE ASSETS, IF REQUESTED.
    if command_line_arguments.export:
        media_station_engine.export(command_line_arguments)

if __name__ == '__main__':
    main()